"""JFPSL legal-template retrieval via Google Vertex AI RAG Engine.

Fetches grounded context from a configured Vertex RAG corpus (legal templates).
Database keyword search can be added later as a secondary source.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _agent_client():
    """Vertex Agent Platform client (ADC on GKE, SA key locally)."""
    import agentplatform
    from google.oauth2 import service_account

    project = settings.gcp_project_id
    location = settings.vertex_rag_location
    creds_file = settings.gcp_service_account_file

    on_gcp = bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_RUN"))
    if creds_file and os.path.isfile(creds_file) and not on_gcp:
        creds = service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return agentplatform.Client(
            project=project, location=location, credentials=creds
        )
    return agentplatform.Client(project=project, location=location)


def search_jfpsl_corpus(query: str, *, max_results: int = 5) -> str:
    """Retrieve legal-template context from Vertex AI RAG Engine."""
    query = (query or "").strip()
    if not query:
        return "Provide a search query about JFPSL legal templates or policies."

    corpus = settings.vertex_rag_corpus_resource
    if not corpus:
        return (
            "Vertex RAG corpus is not configured. Set VERTEX_RAG_CORPUS_ID to your "
            "legal-templates corpus (ID or full resource name)."
        )

    try:
        from google.genai import types as genai_types

        client = _agent_client()
        # top_k belongs on the query, NOT inside VertexRagStore — the API rejects
        # `rag_retrieval_config` there with 400 INVALID_ARGUMENT. The query is passed
        # as a dict because the SDK exposes no public module for RagQuery.
        response = client.rag.retrieve_contexts(
            vertex_rag_store=genai_types.VertexRagStore(
                rag_resources=[
                    genai_types.VertexRagStoreRagResource(rag_corpus=corpus)
                ],
            ),
            query={"text": query, "similarity_top_k": max_results},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Vertex RAG retrieval failed: %s", exc, exc_info=True)
        return (
            "Could not retrieve from the JFPSL legal-templates corpus right now. "
            "Answer from attached context and suggest Legal team review if needed."
        )

    contexts = []
    if response and getattr(response, "contexts", None):
        contexts = list(getattr(response.contexts, "contexts", None) or [])

    if not contexts:
        return (
            f'No matching legal templates found in the Vertex RAG corpus for: "{query}". '
            "Say you could not find an internal template and suggest web_search or Legal review."
        )

    recorded: list[dict] = []
    headers: list[str] = []
    from app.services.gcs_template_library import resolve_library_key_from_rag
    from app.orchestrator.sources import (
        citation_numbers,
        clip_chunk_text,
        clip_snippet,
        dedupe_key,
        make_chunk_id,
        record_sources,
    )

    for ctx in contexts:
        text = (getattr(ctx, "text", None) or "").strip()
        if not text:
            continue
        display_name = getattr(ctx, "source_display_name", None)
        source_uri = getattr(ctx, "source_uri", None)
        source = (
            display_name
            or source_uri
            or getattr(ctx, "source", None)
            or "legal template"
        )
        resolved = resolve_library_key_from_rag(
            str(display_name or source) if display_name or source else None,
            str(source_uri) if source_uri else None,
        )
        kind = "template"
        storage_key: str | None = None
        if resolved:
            kind, storage_key = resolved
        elif str(display_name or "").lower().startswith("executed:"):
            kind = "executed"

        page = _extract_rag_page(ctx, text)
        chunk_body = clip_chunk_text(text)
        chunk_id = make_chunk_id(
            "rag",
            storage_key or str(display_name or source),
            chunk_body[:240],
            str(page or ""),
        )
        recorded.append(
            {
                "kind": kind,
                "title": str(display_name or source),
                "url": str(source_uri or ""),
                "snippet": clip_snippet(text),
                "chunk_text": chunk_body,
                "chunk_id": chunk_id,
                "site": "JFPSL",
                "storage_key": storage_key,
                "page": page,
            }
        )
        score = getattr(ctx, "score", None) or getattr(ctx, "relevance_score", None)
        label = str(source)
        if score is not None:
            label += (
                f" (relevance {score:.3f})"
                if isinstance(score, float)
                else f" (relevance {score})"
            )
        headers.append(label)

    if not recorded:
        return (
            f'No usable excerpts returned from the legal-templates corpus for: "{query}". '
            "Suggest refining the query or escalating to Legal."
        )

    record_sources(recorded)

    # Number from the deduped citation map: an excerpt already cited this turn keeps
    # its number rather than shifting every later citation out of step.
    numbers = citation_numbers()
    lines = [
        f'JFPSL legal templates (Vertex RAG) for: "{query}"',
        f"Corpus: {corpus}",
        "",
    ]
    for i, (item, label) in enumerate(zip(recorded, headers, strict=True), start=1):
        # Falls back to positional numbering when there is no active collection
        # scope (task agents, scripts) — otherwise the model would get no excerpts.
        cite_n = numbers.get(dedupe_key(item)) or i
        lines.append(f"{cite_n}. {label}")
        lines.append(item["chunk_text"])
        lines.append("")

    lines.append(
        "Use these JFPSL template/executed excerpts to ground your answer. "
        "Cite them inline with the absolute numbers shown above (References list order; "
        "attached materials are numbered first when present). "
        "Prefer short verbatim quotes for critical obligations. "
        "Do not invent clauses not present here."
    )
    return "\n".join(lines)


def _extract_rag_page(ctx: object, text: str) -> int | None:
    """Best-effort 1-indexed page from Vertex context metadata or excerpt text."""
    import re

    chunk = getattr(ctx, "chunk", None)
    candidates = [ctx]
    if chunk is not None:
        candidates.insert(0, chunk)

    for obj in candidates:
        for attr in ("page_span", "page_number", "page"):
            val = getattr(obj, attr, None)
            if val is None:
                continue
            if isinstance(val, int) and val > 0:
                return val
            # page_span may be a message with first_page / page_start
            for nested in ("first_page", "page_start", "start_page", "page"):
                n = getattr(val, nested, None)
                if isinstance(n, int) and n > 0:
                    return n
            if isinstance(val, (list, tuple)) and val:
                try:
                    n = int(val[0])
                    if n > 0:
                        return n
                except (TypeError, ValueError):
                    pass
            try:
                n = int(val)
                if n > 0:
                    return n
            except (TypeError, ValueError):
                pass

    m = re.search(r"(?i)\bpage\s*[#:.]?\s*(\d+)\b", text or "")
    if m:
        n = int(m.group(1))
        return n if n > 0 else None
    return None


_RAG_INSUFFICIENT_MARKERS = (
    "Vertex RAG corpus is not configured",
    "Could not retrieve from the JFPSL legal-templates corpus",
    "No matching legal templates found",
    "No usable excerpts returned",
)


def is_rag_insufficient(result: str) -> bool:
    """True when Vertex RAG returned no usable template context."""
    text = (result or "").strip()
    if not text:
        return True
    return any(marker in text for marker in _RAG_INSUFFICIENT_MARKERS)
