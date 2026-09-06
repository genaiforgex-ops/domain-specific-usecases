import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.classification import ClauseResponse
from app.schemas.library import RegulationDocumentResponse
from app.services.library_service import LibraryService
from app.workers.tasks import ingest_library_document_bg

router = APIRouter(prefix="/library", tags=["library"])


def _to_response(document, clause_count: int = 0) -> RegulationDocumentResponse:
    return RegulationDocumentResponse(
        id=document.id,
        regulator=document.regulator,
        instrument=document.instrument,
        source_doc=document.source_doc,
        filename=document.filename,
        status=document.status,
        uploaded_by=document.uploaded_by,
        created_at=document.created_at,
        activated_at=document.activated_at,
        archived_at=document.archived_at,
        clause_count=clause_count,
    )


@router.get("/documents", response_model=list[RegulationDocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:clause_edit")),
):
    svc = LibraryService(db)
    rows = await svc.list_documents()
    return [_to_response(r["document"], r["clause_count"]) for r in rows]


@router.post("/documents", response_model=RegulationDocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    regulator: str = Form(...),
    instrument: str = Form(...),
    source_doc: str = Form(...),
    ref_prefix: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:clause_edit")),
):
    if regulator.upper() not in ("RBI", "SEBI"):
        raise HTTPException(400, "regulator must be RBI or SEBI")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "empty file")

    svc = LibraryService(db)
    document = await svc.create_document(
        regulator.upper(), instrument, source_doc, ref_prefix, file.filename or "upload.pdf", pdf_bytes, user.id
    )

    # Extraction/chunking of a 90-page circular is not instant, so run it off the
    # request path via a background task (same in every environment). Commit first
    # so the task's own DB session sees the row; the document id is returned below
    # for status polling.
    await db.commit()
    background_tasks.add_task(ingest_library_document_bg, str(document.id))

    return _to_response(document)


@router.get("/documents/{document_id}/clauses", response_model=list[ClauseResponse])
async def get_document_clauses(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:clause_edit")),
):
    svc = LibraryService(db)
    return await svc.get_document_clauses(document_id)


@router.post("/documents/{document_id}/activate", response_model=RegulationDocumentResponse)
async def activate_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:clause_edit")),
):
    svc = LibraryService(db)
    try:
        document = await svc.activate_document(document_id, user.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_response(document)


@router.post("/documents/{document_id}/archive", response_model=RegulationDocumentResponse)
async def archive_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:clause_edit")),
):
    svc = LibraryService(db)
    try:
        document = await svc.archive_document(document_id, user.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_response(document)
