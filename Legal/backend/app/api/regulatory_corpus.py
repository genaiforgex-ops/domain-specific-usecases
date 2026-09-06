"""Regulatory knowledge corpus administration.

The legal team downloads official statutes / master directions / circulars and
uploads each against its manifest row here. Ingestion turns the file into citable
clause chunks; this router is the self-serve path (the bulk path is
`backend/scripts/sync_regulatory_to_rag.py`).
"""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.config import settings
from app.core.rbac import Permission
from app.database import get_db
from app.models.user import User
from app.schemas.regulatory_corpus import (
    ChunkOut,
    CorpusDocOut,
    CorpusOverview,
    CorpusTotals,
    IngestResultOut,
    ReindexResult,
)
from app.services.audit_service import write_audit
from app.services.regulatory_ingest_service import (
    IngestError,
    apply_supersession,
    corpus_status,
    corpus_totals,
    delete_document,
    document_chunks,
    fetch_direct,
    ingest_document,
    mark_stale,
    reindex_embeddings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/regulatory-corpus", tags=["regulatory-corpus"])

# Corpus content is governance, same bar as the template library / playbooks.
_MANAGE = Permission.PLAYBOOK_MANAGEMENT


@router.get("", response_model=CorpusOverview)
def corpus_overview(
    _: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> CorpusOverview:
    """Every manifest row with its ingestion state, plus totals."""
    mark_stale(db)
    return CorpusOverview(
        totals=CorpusTotals(**corpus_totals(db)),
        documents=[CorpusDocOut(**vars(row)) for row in corpus_status(db)],
    )


@router.post("/{doc_id}/upload", response_model=IngestResultOut)
async def upload_regulatory_document(
    doc_id: str,
    request: Request,
    file: UploadFile = File(...),
    force: bool = Query(default=False),
    user: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> IngestResultOut:
    """Ingest a downloaded official document against its manifest row."""
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty"
        )
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB limit",
        )

    try:
        result = ingest_document(
            db,
            doc_id=doc_id,
            data=data,
            filename=file.filename or f"{doc_id}.pdf",
            user_id=user.id,
            mime_type=file.content_type,
            force=force,
        )
    except IngestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_audit(
        db,
        user=user,
        action_type="regulatory_corpus_ingest",
        module="regulatory_corpus",
        input_summary=f"{doc_id} ({file.filename})",
        ai_output_summary=f"{result.chunk_count} clauses / {result.page_count} pages",
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    return IngestResultOut(**vars(result))


@router.post("/{doc_id}/fetch", response_model=IngestResultOut)
def fetch_regulatory_document(
    doc_id: str,
    request: Request,
    force: bool = Query(default=False),
    user: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> IngestResultOut:
    """Download and ingest a manifest row that carries a direct official PDF URL."""
    try:
        result = fetch_direct(db, doc_id, user_id=user.id, force=force)
    except IngestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    write_audit(
        db,
        user=user,
        action_type="regulatory_corpus_fetch",
        module="regulatory_corpus",
        input_summary=doc_id,
        ai_output_summary=f"{result.chunk_count} clauses / {result.page_count} pages",
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    return IngestResultOut(**vars(result))


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def list_document_chunks(
    doc_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> list[ChunkOut]:
    """Clause chunks in document order — verify labels before trusting citations."""
    try:
        rows = document_chunks(db, doc_id, limit=limit, offset=offset)
    except IngestError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [ChunkOut.model_validate(r) for r in rows]


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_regulatory_document(
    doc_id: str,
    request: Request,
    user: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> None:
    if not delete_document(db, doc_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{doc_id} is not ingested"
        )
    write_audit(
        db,
        user=user,
        action_type="regulatory_corpus_delete",
        module="regulatory_corpus",
        input_summary=doc_id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()


@router.post("/reindex", response_model=ReindexResult)
def reindex_corpus(
    doc_id: str | None = Query(default=None),
    _: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> ReindexResult:
    """Re-embed stored clauses after an embedding model/dimension change."""
    try:
        count = reindex_embeddings(db, doc_id=doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Regulatory reindex failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Reindex failed: {exc}",
        ) from exc
    return ReindexResult(reindexed=count)


@router.post("/supersession", response_model=ReindexResult)
def refresh_supersession(
    _: User = Depends(require_permission(_MANAGE)),
    db: Session = Depends(get_db),
) -> ReindexResult:
    """Re-resolve which ingested documents have been replaced."""
    return ReindexResult(reindexed=apply_supersession(db))
