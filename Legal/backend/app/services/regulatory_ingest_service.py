"""Ingest official regulatory documents into the clause corpus.

The legal team downloads a PDF from the regulator's own site and hands it to a
manifest row; this module turns it into citable clause chunks. Nothing is ingested
without a manifest row, so every clause in the corpus traces back to an official
source URL.

Sequence per document:
  validate doc_id → sha256 (skip unchanged) → store original → extract pages →
  clause-aware chunk → embed → replace chunks atomically → resolve supersession
  → optionally push text to the Vertex recall corpus (non-fatal)
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.regulatory_corpus import (
    STATUS_FAILED,
    STATUS_INGESTED,
    STATUS_MISSING,
    STATUS_STALE,
    RegulatoryChunk,
    RegulatoryDocument,
)
from app.services import embedding_service, regulatory_vertex_recall
from app.services.clause_chunker import (
    ClauseChunk,
    ClauseChunkError,
    chunk_clauses,
    chunk_key as build_chunk_key,
    extract_pages,
)
from app.services.document_storage import get_regulatory_storage
from app.services.regulatory_manifest import (
    ManifestError,
    ManifestRow,
    load_manifest,
    manifest_row,
    require_row,
)

logger = logging.getLogger(__name__)


class IngestError(Exception):
    """Raised when a document cannot be ingested."""


@dataclass
class IngestResult:
    doc_id: str
    status: str
    chunk_count: int = 0
    page_count: int = 0
    skipped: bool = False
    message: str = ""


@dataclass
class DocStatus:
    """A manifest row joined with whatever has been ingested for it."""

    doc_id: str
    title: str
    issuer: str
    domain: str
    doc_type: str
    priority: str
    update_cadence: str
    download_mode: str
    official_url: str | None
    direct_pdf_url: str | None
    version_or_effective: str
    effective_date: str | None
    status: str
    chunk_count: int = 0
    page_count: int = 0
    ingested_at: str | None = None
    superseded_by: str | None = None
    supersedes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    storage_key: str | None = None
    last_error: str | None = None
    can_auto_fetch: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _invalidate_retrieval_cache() -> None:
    """Drop the in-process embedding matrix so new clauses are searchable at once.

    Imported lazily: the retrieval service imports this module's models, and a
    top-level import here would close the cycle.
    """
    from app.services import regulatory_rag_service

    regulatory_rag_service.invalidate_cache()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_document(db: Session, doc_id: str) -> RegulatoryDocument | None:
    return db.execute(
        select(RegulatoryDocument).where(RegulatoryDocument.doc_id == doc_id)
    ).scalar_one_or_none()


def _apply_manifest_fields(doc: RegulatoryDocument, row: ManifestRow) -> None:
    """Manifest is the source of truth for descriptive metadata."""
    doc.domain = row.domain
    doc.title = row.title
    doc.issuer = row.issuer
    doc.doc_type = row.doc_type
    doc.priority = row.priority
    doc.update_cadence = row.update_cadence
    doc.canonical_url = row.official_url
    doc.direct_pdf_url = row.direct_pdf_url
    doc.version_or_effective = row.version_or_effective
    doc.effective_date = row.effective_date
    doc.supersedes = "; ".join(row.supersedes) if row.supersedes else None
    doc.tags = row.tags or []


def _unique_chunk_keys(doc_id: str, chunks: list[ClauseChunk]) -> list[str]:
    """Chunk keys, de-duplicated — issuers do reuse numbering across chapters."""
    seen: dict[str, int] = {}
    keys: list[str] = []
    for chunk in chunks:
        base = build_chunk_key(doc_id, chunk)
        count = seen.get(base, 0)
        seen[base] = count + 1
        keys.append(base if count == 0 else f"{base}-{count + 1}"[:160])
    return keys


def ingest_document(
    db: Session,
    *,
    doc_id: str,
    data: bytes,
    filename: str,
    user_id: int | None = None,
    mime_type: str | None = None,
    force: bool = False,
) -> IngestResult:
    """Ingest one manifest document from raw bytes. Commits on success."""
    doc_id = (doc_id or "").strip()
    try:
        row = require_row(doc_id)
    except ManifestError as exc:
        raise IngestError(str(exc)) from exc
    if not data:
        raise IngestError(f"No file content supplied for {doc_id}")

    digest = _sha256(data)
    doc = _get_document(db, doc_id)

    if (
        doc is not None
        and not force
        and doc.source_sha256 == digest
        and doc.status == STATUS_INGESTED
        and doc.chunk_count > 0
    ):
        # Same bytes already chunked and embedded — re-embedding would just burn quota.
        _apply_manifest_fields(doc, row)
        db.commit()
        return IngestResult(
            doc_id=doc_id,
            status=doc.status,
            chunk_count=doc.chunk_count,
            page_count=doc.page_count,
            skipped=True,
            message="Unchanged since last ingest",
        )

    if doc is None:
        doc = RegulatoryDocument(doc_id=doc_id, status=STATUS_MISSING)
        db.add(doc)
    _apply_manifest_fields(doc, row)

    try:
        pages = extract_pages(data, filename, mime_type)
        chunks = chunk_clauses(pages, doc_type=row.doc_type, doc_id=doc_id)
        if not chunks:
            raise ClauseChunkError("No clause chunks produced")

        vectors = embedding_service.embed_documents([c.text for c in chunks])
        keys = _unique_chunk_keys(doc_id, chunks)

        content_type = mime_type or mimetypes.guess_type(filename)[0] or "application/pdf"
        storage_key, _ = get_regulatory_storage().upload(data, filename, content_type)

        # Replace the previous revision wholesale — a partial overlay would leave
        # clauses from a repealed version behind.
        db.flush()
        db.execute(delete(RegulatoryChunk).where(RegulatoryChunk.doc_id == doc_id))
        for chunk, key, vector in zip(chunks, keys, vectors, strict=True):
            db.add(
                RegulatoryChunk(
                    document_id=doc.id,
                    doc_id=doc_id,
                    chunk_key=key,
                    section_label=chunk.section_label,
                    parent_heading=chunk.parent_heading,
                    ordinal=chunk.ordinal,
                    page=chunk.page,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=vector,
                )
            )

        doc.storage_key = storage_key
        doc.source_filename = filename
        doc.source_sha256 = digest
        doc.page_count = len(pages)
        doc.chunk_count = len(chunks)
        doc.status = STATUS_INGESTED
        doc.last_error = None
        doc.ingested_at = _now()
        if user_id is not None:
            doc.ingested_by_id = user_id
        db.commit()
    except Exception as exc:  # noqa: BLE001 - surface the reason on the row
        db.rollback()
        doc = _get_document(db, doc_id)
        if doc is None:
            doc = RegulatoryDocument(doc_id=doc_id, status=STATUS_FAILED)
            _apply_manifest_fields(doc, row)
            db.add(doc)
        doc.status = STATUS_FAILED
        doc.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        logger.exception("Regulatory ingest failed for %s", doc_id)
        raise IngestError(f"Ingest failed for {doc_id}: {exc}") from exc

    apply_supersession(db)
    _invalidate_retrieval_cache()

    # Best-effort second recall channel. Runs after the commit so a Vertex outage
    # can never fail an ingest or roll back clauses that are already correct.
    if regulatory_vertex_recall.is_active():
        file_name = regulatory_vertex_recall.sync_document(
            doc_id, "\n\n".join(pages), previous_file_name=doc.vertex_file_name
        )
        if file_name:
            doc.vertex_file_name = file_name
            db.commit()

    logger.info(
        "Ingested %s: %d pages, %d clause chunks", doc_id, doc.page_count, doc.chunk_count
    )
    return IngestResult(
        doc_id=doc_id,
        status=doc.status,
        chunk_count=doc.chunk_count,
        page_count=doc.page_count,
        message="Ingested",
    )


def fetch_direct(
    db: Session, doc_id: str, *, user_id: int | None = None, force: bool = False
) -> IngestResult:
    """Download and ingest a manifest row that carries a direct PDF URL."""
    row = require_row(doc_id)
    if not row.can_auto_fetch or not row.direct_pdf_url:
        raise IngestError(
            f"{doc_id} is download_mode={row.download_mode} — upload the file manually"
        )

    import httpx

    try:
        response = httpx.get(
            row.direct_pdf_url,
            follow_redirects=True,
            timeout=60.0,
            headers={"User-Agent": "LegalOS-RegulatoryCorpus/1.0"},
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"Could not download {row.direct_pdf_url}: {exc}") from exc

    filename = row.direct_pdf_url.split("/")[-1].split("?")[0] or f"{doc_id}.pdf"
    return ingest_document(
        db,
        doc_id=doc_id,
        data=response.content,
        filename=filename,
        user_id=user_id,
        mime_type=response.headers.get("content-type"),
        force=force,
    )


def apply_supersession(db: Session) -> int:
    """Point superseded documents at their replacement.

    The manifest names what a document replaces in prose ("2022 Digital Lending
    Guidelines"), so a replaced *doc_id* is only set when the text actually matches
    another ingested doc_id or its title. Everything else stays None rather than
    guessing — wrongly flagging a live rule as repealed would hide current law.
    """
    docs = db.execute(select(RegulatoryDocument)).scalars().all()
    by_id = {d.doc_id.lower(): d for d in docs}
    by_title = {(d.title or "").strip().lower(): d for d in docs}

    changed = 0
    for doc in docs:
        for raw in (doc.supersedes or "").split(";"):
            token = raw.strip().lower()
            if not token:
                continue
            target = by_id.get(token) or by_title.get(token)
            if target is None or target.doc_id == doc.doc_id:
                continue
            if target.superseded_by != doc.doc_id:
                target.superseded_by = doc.doc_id
                changed += 1
                logger.info("%s marked superseded by %s", target.doc_id, doc.doc_id)
    if changed:
        db.commit()
    return changed


def mark_stale(db: Session) -> int:
    """Flag ingested docs whose manifest version has moved on.

    Manual-download rows cannot be refreshed automatically, so this is how the
    admin page tells the legal team to go and re-download one.
    """
    changed = 0
    for doc_id, row in load_manifest().items():
        doc = _get_document(db, doc_id)
        if doc is None or doc.status != STATUS_INGESTED:
            continue
        if row.version_or_effective and doc.version_or_effective != row.version_or_effective:
            doc.status = STATUS_STALE
            doc.version_or_effective = row.version_or_effective
            doc.effective_date = row.effective_date
            changed += 1
    if changed:
        db.commit()
    return changed


def refresh_corpus(db: Session) -> dict[str, int]:
    """Re-check documents whose cadence says they change, and flag the rest.

    Only rows with a direct official URL can be refreshed automatically; the sha256
    comparison inside `ingest_document` means an unchanged file costs one download
    and no embedding calls. Manual-download rows are flagged `stale` instead, which
    is how the admin page tells the legal team to fetch a new copy. `stable` rows
    (bare Acts) are never touched — they change only by amendment.
    """
    auto_cadences = {"on-change", "monthly", "quarterly"}
    result = {"checked": 0, "reingested": 0, "unchanged": 0, "failed": 0}

    for doc_id, row in load_manifest().items():
        if row.update_cadence not in auto_cadences:
            continue
        if not row.can_auto_fetch:
            continue
        doc = _get_document(db, doc_id)
        if doc is None or doc.status not in (STATUS_INGESTED, STATUS_STALE):
            # Never ingested — leave it to a human; auto-loading a document nobody
            # has reviewed is not the same as refreshing one.
            continue
        result["checked"] += 1
        try:
            outcome = fetch_direct(db, doc_id)
        except IngestError as exc:
            result["failed"] += 1
            logger.warning("Refresh failed for %s: %s", doc_id, exc)
            continue
        if outcome.skipped:
            result["unchanged"] += 1
        else:
            result["reingested"] += 1
            logger.info("%s re-ingested after upstream change", doc_id)

    result["flagged_stale"] = mark_stale(db)
    return result


def delete_document(db: Session, doc_id: str) -> bool:
    doc = _get_document(db, doc_id)
    if doc is None:
        return False
    regulatory_vertex_recall.delete_document_file(doc.vertex_file_name)
    db.execute(delete(RegulatoryChunk).where(RegulatoryChunk.doc_id == doc_id))
    db.delete(doc)
    db.commit()
    _invalidate_retrieval_cache()
    logger.info("Deleted regulatory document %s", doc_id)
    return True


def corpus_status(db: Session) -> list[DocStatus]:
    """Every manifest row with its ingestion state, P1 first."""
    rows = load_manifest()
    docs = {
        d.doc_id: d
        for d in db.execute(select(RegulatoryDocument)).scalars().all()
    }

    out: list[DocStatus] = []
    for doc_id, row in rows.items():
        doc = docs.get(doc_id)
        out.append(
            DocStatus(
                doc_id=doc_id,
                title=row.title,
                issuer=row.issuer,
                domain=row.domain,
                doc_type=row.doc_type,
                priority=row.priority,
                update_cadence=row.update_cadence,
                download_mode=row.download_mode,
                official_url=row.official_url,
                direct_pdf_url=row.direct_pdf_url,
                version_or_effective=row.version_or_effective,
                effective_date=row.effective_date.isoformat() if row.effective_date else None,
                status=doc.status if doc else STATUS_MISSING,
                chunk_count=doc.chunk_count if doc else 0,
                page_count=doc.page_count if doc else 0,
                ingested_at=doc.ingested_at.isoformat() if doc and doc.ingested_at else None,
                superseded_by=doc.superseded_by if doc else None,
                supersedes=row.supersedes,
                tags=row.tags,
                storage_key=doc.storage_key if doc else None,
                last_error=doc.last_error if doc else None,
                can_auto_fetch=row.can_auto_fetch,
            )
        )
    out.sort(key=lambda d: (d.priority, d.domain, d.doc_id))
    return out


def corpus_totals(db: Session) -> dict[str, int]:
    ingested = db.execute(
        select(func.count())
        .select_from(RegulatoryDocument)
        .where(RegulatoryDocument.status == STATUS_INGESTED)
    ).scalar_one()
    chunks = db.execute(select(func.count()).select_from(RegulatoryChunk)).scalar_one()
    return {
        "manifest_total": len(load_manifest()),
        "ingested": int(ingested),
        "chunks": int(chunks),
    }


def document_chunks(
    db: Session, doc_id: str, *, limit: int = 50, offset: int = 0
) -> list[RegulatoryChunk]:
    """Clause chunks in document order — used to eyeball chunking quality."""
    if manifest_row(doc_id) is None:
        raise IngestError(f"Unknown doc_id '{doc_id}'")
    return list(
        db.execute(
            select(RegulatoryChunk)
            .where(RegulatoryChunk.doc_id == doc_id)
            .order_by(RegulatoryChunk.ordinal)
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
        )
        .scalars()
        .all()
    )


def reindex_embeddings(db: Session, *, doc_id: str | None = None) -> int:
    """Re-embed stored chunks in place (after a model or dimension change)."""
    stmt = select(RegulatoryChunk).order_by(RegulatoryChunk.id)
    if doc_id:
        stmt = stmt.where(RegulatoryChunk.doc_id == doc_id)
    chunks = list(db.execute(stmt).scalars().all())
    if not chunks:
        return 0

    vectors = embedding_service.embed_documents([c.text for c in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
    db.commit()
    _invalidate_retrieval_cache()
    logger.info("Re-embedded %d chunks%s", len(chunks), f" for {doc_id}" if doc_id else "")
    return len(chunks)
