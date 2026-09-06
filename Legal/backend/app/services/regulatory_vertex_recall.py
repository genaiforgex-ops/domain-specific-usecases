"""Optional Vertex AI RAG recall channel for the regulatory corpus.

Postgres is authoritative for clause text, labels and supersession. Vertex adds a
second, purely *document-level* recall signal: given a query it answers "which
documents look relevant", and Postgres then supplies the exact clauses inside them.

One RagFile per document, not per clause — Vertex only chunks by fixed character
length, so per-clause files would mean thousands of uploads for recall Postgres
already provides. Every function here degrades to a no-op / empty result when the
corpus is unconfigured or the API errors, so this channel can never break an answer.
"""

from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)

# display_name prefix that marks a regulatory document inside the corpus.
DISPLAY_PREFIX = "reg:"


@lru_cache(maxsize=1)
def _client():
    import agentplatform
    from google.oauth2 import service_account

    project = settings.gcp_project_id
    location = settings.vertex_rag_location
    creds_file = settings.gcp_service_account_file

    on_gcp = bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_RUN"))
    if creds_file and os.path.isfile(creds_file) and not on_gcp:
        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return agentplatform.Client(project=project, location=location, credentials=creds)
    return agentplatform.Client(project=project, location=location)


def is_active() -> bool:
    return settings.regulatory_vertex_sync_active


def display_name_for(doc_id: str) -> str:
    return f"{DISPLAY_PREFIX}{doc_id}"


def doc_id_from_display_name(display_name: str | None) -> str | None:
    raw = (display_name or "").strip()
    if not raw.lower().startswith(DISPLAY_PREFIX):
        return None
    return raw[len(DISPLAY_PREFIX) :].strip() or None


def sync_document(doc_id: str, text: str, *, previous_file_name: str | None = None) -> str | None:
    """Upload a document's text as a single RagFile. Returns its resource name.

    Non-fatal: returns None on any failure, since the Postgres index alone already
    answers correctly.
    """
    if not is_active():
        return None
    corpus = settings.regulatory_vertex_corpus_resource
    if not corpus or not (text or "").strip():
        return None

    if previous_file_name:
        delete_document_file(previous_file_name)

    path = None
    try:
        client = _client()
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(text)
            path = fh.name
        uploaded = client.rag.upload_file(
            corpus_name=corpus, path=path, display_name=display_name_for(doc_id)[:120]
        )
        name = getattr(uploaded, "name", None)
        logger.info("Synced %s to Vertex regulatory corpus (%s)", doc_id, name)
        return str(name) if name else None
    except Exception as exc:  # noqa: BLE001 - recall channel is best-effort
        logger.warning("Vertex sync skipped for %s: %s", doc_id, exc)
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def delete_document_file(file_name: str | None) -> None:
    """Remove a previously uploaded RagFile so revisions don't accumulate."""
    if not file_name or not is_active():
        return
    try:
        _client().rag.delete_file(name=file_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not delete Vertex file %s: %s", file_name, exc)


def recall_doc_ids(query: str, *, top_k: int = 10) -> dict[str, float]:
    """Best doc_id → score map for a query. Empty when the channel is inactive."""
    if not is_active():
        return {}
    corpus = settings.regulatory_vertex_corpus_resource
    query = (query or "").strip()
    if not corpus or not query:
        return {}

    try:
        from google.genai import types as genai_types

        # top_k belongs on the query; passing rag_retrieval_config inside
        # VertexRagStore is rejected with 400 INVALID_ARGUMENT.
        response = _client().rag.retrieve_contexts(
            vertex_rag_store=genai_types.VertexRagStore(
                rag_resources=[
                    genai_types.VertexRagStoreRagResource(rag_corpus=corpus)
                ],
            ),
            query={"text": query, "similarity_top_k": top_k},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vertex regulatory recall failed: %s", exc)
        return {}

    contexts = []
    if response and getattr(response, "contexts", None):
        contexts = list(getattr(response.contexts, "contexts", None) or [])

    scores: dict[str, float] = {}
    for ctx in contexts:
        doc_id = doc_id_from_display_name(getattr(ctx, "source_display_name", None))
        if not doc_id:
            continue
        raw = getattr(ctx, "score", None)
        try:
            score = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        # Keep the strongest hit per document.
        scores[doc_id] = max(scores.get(doc_id, 0.0), score)
    return scores
