"""Clause-level retrieval over the regulatory corpus.

Three recall channels, fused by Reciprocal Rank Fusion:

  1. keyword  — Postgres `ts_rank_cd` over the generated tsvector. This is what
                finds "Section 43A", "Form 60" or "V-CIP", which pure vector
                search reliably misses.
  2. semantic — cosine over cached float32 vectors (numpy matmul; pgvector is not
                available on this instance).
  3. vertex   — optional document-level recall; contributes a rank boost only.

RRF is used instead of raw score blending because the channels' scores are not
comparable (ts_rank_cd is unbounded, cosine is [-1,1], Vertex is its own scale) —
ranks are. No cross-encoder reranker is installed, so the tie-breakers are a small
P1-priority boost and the Vertex signal.

Then the as-of filter drops anything superseded or not yet in force, which is what
stops the bot citing repealed rules that are still in the corpus for history.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np
from sqlalchemy import func, select, text as sql_text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.regulatory_corpus import (
    STATUS_INGESTED,
    RegulatoryChunk,
    RegulatoryDocument,
)
from app.services import embedding_service, regulatory_vertex_recall

logger = logging.getLogger(__name__)

# RRF damping. 60 is the standard constant from the original paper; it keeps a
# top-3 hit in one channel from being swamped by a long tail in the other.
_RRF_K = 60
_CANDIDATES_PER_CHANNEL = 40
# Additive nudges, deliberately smaller than one rank step at the top of the list.
_VERTEX_BOOST = 0.004
_P1_BOOST = 0.002

_INSUFFICIENT = (
    "No matching provision found in the regulatory corpus for: "
)


@dataclass
class RetrievedClause:
    """One clause chunk with everything a citation needs."""

    chunk_key: str
    doc_id: str
    title: str
    issuer: str
    doc_type: str
    domain: str
    section_label: str | None
    parent_heading: str | None
    page: int
    text: str
    canonical_url: str | None
    effective_date: date | None
    superseded_by: str | None
    storage_key: str | None
    priority: str
    score: float

    @property
    def citation_label(self) -> str:
        """What the cite chip shows, e.g. "RBI (Digital Lending) Directions, 2025, Para 5.3"."""
        if self.section_label:
            return f"{self.title}, {self.section_label}"
        return self.title


# ── Embedding matrix cache ───────────────────────────────────────────────────
# Vectors live in Postgres but similarity is computed in-process. At corpus scale
# (tens of thousands of clauses × 768 dims) this is tens of MB and a few ms per
# query, so a cached matrix beats a round-trip per candidate.
_lock = threading.Lock()
_matrix: np.ndarray | None = None
_chunk_ids: list[int] = []
_generation: tuple | None = None


def invalidate_cache() -> None:
    """Drop the cached matrix. Called after ingest/reindex in this process."""
    global _matrix, _chunk_ids, _generation
    with _lock:
        _matrix = None
        _chunk_ids = []
        _generation = None


def _current_generation(db: Session) -> tuple:
    """Cheap fingerprint so another process's ingest is picked up without a restart."""
    row = db.execute(
        select(
            func.count(RegulatoryChunk.id),
            func.coalesce(func.max(RegulatoryChunk.id), 0),
            func.coalesce(func.sum(func.length(RegulatoryChunk.embedding)), 0),
        )
    ).one()
    return tuple(int(v or 0) for v in row)


def _ensure_matrix(db: Session) -> tuple[np.ndarray | None, list[int]]:
    global _matrix, _chunk_ids, _generation

    generation = _current_generation(db)
    with _lock:
        if _matrix is not None and _generation == generation:
            return _matrix, _chunk_ids

    rows = db.execute(
        select(RegulatoryChunk.id, RegulatoryChunk.embedding).order_by(RegulatoryChunk.id)
    ).all()

    ids: list[int] = []
    vectors: list[np.ndarray] = []
    for chunk_id, blob in rows:
        vec = embedding_service.from_bytes(blob)
        if vec is None:
            continue
        ids.append(int(chunk_id))
        vectors.append(vec)

    matrix = np.vstack(vectors) if vectors else None
    with _lock:
        _matrix, _chunk_ids, _generation = matrix, ids, generation
    if matrix is not None:
        logger.info(
            "Regulatory embedding cache: %d vectors × %d dims (%.1f MB)",
            matrix.shape[0],
            matrix.shape[1],
            matrix.nbytes / 1e6,
        )
    return matrix, ids


# ── Filters ─────────────────────────────────────────────────────────────────
def _allowed_doc_ids(
    db: Session,
    *,
    domains: Sequence[str] | None,
    doc_types: Sequence[str] | None,
    as_of: date | None,
    include_superseded: bool,
) -> set[str]:
    """doc_ids that pass the metadata + as-of/supersession filter."""
    stmt = select(RegulatoryDocument.doc_id).where(
        RegulatoryDocument.status == STATUS_INGESTED
    )
    if domains:
        stmt = stmt.where(RegulatoryDocument.domain.in_(list(domains)))
    if doc_types:
        stmt = stmt.where(RegulatoryDocument.doc_type.in_(list(doc_types)))
    if not include_superseded:
        stmt = stmt.where(RegulatoryDocument.superseded_by.is_(None))
        if as_of is not None:
            # A document with no parsed date is a living document (regulator updates
            # it in place) — keep it rather than filtering current law out.
            stmt = stmt.where(
                (RegulatoryDocument.effective_date.is_(None))
                | (RegulatoryDocument.effective_date <= as_of)
            )
    return {row for row in db.execute(stmt).scalars().all()}


# ── Recall channels ─────────────────────────────────────────────────────────
def _keyword_ranking(db: Session, query: str, *, limit: int) -> list[int]:
    """Chunk ids ranked by Postgres full-text relevance."""
    stmt = sql_text(
        """
        SELECT c.id
        FROM regulatory_chunks c,
             websearch_to_tsquery('english', :q) AS q
        WHERE c.tsv @@ q
        ORDER BY ts_rank_cd(c.tsv, q) DESC, c.id
        LIMIT :lim
        """
    )
    try:
        rows = db.execute(stmt, {"q": query, "lim": limit}).scalars().all()
    except Exception as exc:  # noqa: BLE001 - a malformed tsquery must not fail the turn
        logger.warning("Keyword channel failed: %s", exc)
        return []
    return [int(r) for r in rows]


def _semantic_ranking(db: Session, query: str, *, limit: int) -> list[int]:
    """Chunk ids ranked by cosine similarity (dot product on normalized vectors)."""
    matrix, ids = _ensure_matrix(db)
    if matrix is None or not ids:
        return []
    try:
        q = embedding_service.embed_query(query)
    except Exception as exc:  # noqa: BLE001 - degrade to keyword-only
        logger.warning("Semantic channel failed: %s", exc)
        return []

    scores = matrix @ q
    take = min(limit, scores.shape[0])
    top = np.argpartition(-scores, take - 1)[:take]
    top = top[np.argsort(-scores[top])]
    return [ids[i] for i in top]


def _rrf(rankings: Iterable[list[int]]) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
    return fused


def fuse_rankings(
    rankings: Sequence[list[int]],
    *,
    doc_id_by_chunk: dict[int, str] | None = None,
    vertex_scores: dict[str, float] | None = None,
    priority_by_doc: dict[str, str] | None = None,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion plus small Vertex / P1 nudges. Pure function."""
    fused = _rrf(rankings)
    if doc_id_by_chunk:
        for chunk_id in list(fused):
            doc_id = doc_id_by_chunk.get(chunk_id)
            if not doc_id:
                continue
            if vertex_scores and doc_id in vertex_scores:
                fused[chunk_id] += _VERTEX_BOOST
            if priority_by_doc and priority_by_doc.get(doc_id) == "P1":
                fused[chunk_id] += _P1_BOOST
    return sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))


# ── Public API ──────────────────────────────────────────────────────────────
def search_regulatory(
    db: Session,
    query: str,
    *,
    domains: Sequence[str] | None = None,
    doc_types: Sequence[str] | None = None,
    as_of: date | None = None,
    include_superseded: bool = False,
    top_k: int | None = None,
) -> list[RetrievedClause]:
    """Retrieve the most relevant in-force clauses for a query."""
    query = (query or "").strip()
    if not query:
        return []
    limit = int(top_k or settings.regulatory_rag_max_results)
    effective_as_of = as_of if as_of is not None else date.today()

    allowed = _allowed_doc_ids(
        db,
        domains=domains,
        doc_types=doc_types,
        as_of=effective_as_of,
        include_superseded=include_superseded,
    )
    if not allowed:
        return []

    keyword = _keyword_ranking(db, query, limit=_CANDIDATES_PER_CHANNEL)
    semantic = _semantic_ranking(db, query, limit=_CANDIDATES_PER_CHANNEL)
    candidate_ids = list(dict.fromkeys([*keyword, *semantic]))
    if not candidate_ids:
        return []

    rows = db.execute(
        select(RegulatoryChunk, RegulatoryDocument)
        .join(RegulatoryDocument, RegulatoryChunk.document_id == RegulatoryDocument.id)
        .where(RegulatoryChunk.id.in_(candidate_ids))
    ).all()
    by_chunk = {chunk.id: (chunk, doc) for chunk, doc in rows if doc.doc_id in allowed}
    if not by_chunk:
        return []

    # Drop filtered-out chunks before fusing so ranks reflect eligible results only.
    keyword = [cid for cid in keyword if cid in by_chunk]
    semantic = [cid for cid in semantic if cid in by_chunk]

    vertex_scores = regulatory_vertex_recall.recall_doc_ids(query, top_k=10)
    if vertex_scores:
        vertex_scores = {k: v for k, v in vertex_scores.items() if k in allowed}

    ranked = fuse_rankings(
        [keyword, semantic],
        doc_id_by_chunk={cid: doc.doc_id for cid, (_, doc) in by_chunk.items()},
        vertex_scores=vertex_scores,
        priority_by_doc={doc.doc_id: doc.priority for _, (_, doc) in by_chunk.items()},
    )

    out: list[RetrievedClause] = []
    for chunk_id, score in ranked[:limit]:
        chunk, doc = by_chunk[chunk_id]
        out.append(
            RetrievedClause(
                chunk_key=chunk.chunk_key,
                doc_id=doc.doc_id,
                title=doc.title,
                issuer=doc.issuer,
                doc_type=doc.doc_type,
                domain=doc.domain,
                section_label=chunk.section_label,
                parent_heading=chunk.parent_heading,
                page=chunk.page,
                text=chunk.text,
                canonical_url=doc.canonical_url,
                effective_date=doc.effective_date,
                superseded_by=doc.superseded_by,
                storage_key=doc.storage_key,
                priority=doc.priority,
                score=float(score),
            )
        )
    return out


def format_clauses_for_model(query: str, clauses: Sequence[RetrievedClause]) -> str:
    """Render clauses as numbered, citable context and record them as Sources.

    Citation numbers are absolute across the whole turn (attachments first, then
    prior tool hits), matching `jfpsl_rag_service` so `[n]` markers line up with
    the References list.
    """
    from app.orchestrator.sources import (
        citation_numbers,
        clip_chunk_text,
        clip_snippet,
        dedupe_key,
        record_sources,
    )

    if not clauses:
        return (
            f'{_INSUFFICIENT}"{query}". '
            "Say the corpus has no provision on this and offer web_search or Legal review."
        )

    recorded: list[dict] = []
    for clause in clauses:
        body = clip_chunk_text(clause.text)
        recorded.append(
            {
                "kind": "regulation",
                "title": clause.title,
                "url": clause.canonical_url,
                "snippet": clip_snippet(clause.text),
                "chunk_text": body,
                "chunk_id": clause.chunk_key,
                "site": clause.issuer,
                "storage_key": clause.storage_key,
                "page": clause.page,
                "doc_id": clause.doc_id,
                "section_label": clause.section_label,
                "issuer": clause.issuer,
                "effective_date": (
                    clause.effective_date.isoformat() if clause.effective_date else None
                ),
                "superseded_by": clause.superseded_by,
                "canonical_url": clause.canonical_url,
            }
        )

    record_sources(recorded)

    # Number from the deduped citation map so a clause already cited earlier in the
    # turn keeps its number instead of shifting every later citation.
    numbers = citation_numbers()
    lines = [f'Indian financial-services law (regulatory corpus) for: "{query}"', ""]
    for i, (clause, item) in enumerate(zip(clauses, recorded, strict=True), start=1):
        # Falls back to positional numbering when there is no active collection
        # scope (task agents, scripts) — otherwise the model would get no clauses.
        cite_n = numbers.get(dedupe_key(item)) or i
        header = f"{cite_n}. {clause.citation_label} — {clause.issuer}"
        if clause.effective_date:
            header += f" (effective {clause.effective_date.isoformat()})"
        lines.append(header)
        if clause.parent_heading:
            lines.append(f"[{clause.parent_heading}]")
        lines.append(item["chunk_text"])
        lines.append("")

    lines.append(
        "Cite these by their bracket number and name the provision "
        "(e.g. “[1] Para 5.3”). Do not invent clause numbers or dates."
    )
    return "\n".join(lines)


def search_regulatory_corpus(query: str, *, max_results: int | None = None) -> str:
    """Tool-facing entry point: own DB session, routed filters, formatted output."""
    from app.database import SessionLocal
    from app.services.regulatory_router import route_query

    query = (query or "").strip()
    if not query:
        return "Provide a question about Indian financial-services law."

    route = route_query(query)
    db = SessionLocal()
    try:
        clauses = search_regulatory(
            db,
            query,
            domains=route.domains or None,
            include_superseded=route.include_superseded,
            top_k=max_results,
        )
        return format_clauses_for_model(query, clauses)
    except Exception as exc:  # noqa: BLE001 - never break a chat turn
        logger.exception("Regulatory retrieval failed: %s", exc)
        return (
            "Could not search the regulatory corpus right now. "
            "Fall back to web_search of official regulator sites and flag for Legal review."
        )
    finally:
        db.close()


def is_corpus_insufficient(result: str) -> bool:
    """True when the corpus had nothing — mirrors `jfpsl_rag_service.is_rag_insufficient`."""
    lowered = (result or "").lower()
    return _INSUFFICIENT.strip().lower() in lowered or "could not search" in lowered
