import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response as FastResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.factory import get_storage_adapter
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.classification import ClassificationJob, RegulationDocument, RegulatorClause
from app.models.document import Document
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.classification import (
    ClassificationConfirm,
    ClassificationOverride,
    ClassificationResponse,
    ClauseCreate,
    ClauseResponse,
)
from app.services.agent_service import AgentService
from app.services.ai_gateway import AIGateway
from app.services.classification_service import ClassificationService
from app.services.document_extract import extract_canonical_fields, extract_text
from app.services.reporting_service import ReportingService
from app.workers.tasks import run_classification_bg

router = APIRouter(tags=["classifications"])


def _slug(text: str, fallback: str = "unknown") -> str:
    """URL/path-safe slug: alphanumerics joined by single hyphens."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip()).strip("-")
    return s or fallback


async def _find_regulation_document(
    db: AsyncSession, regulator: str, instrument: str
) -> RegulationDocument | None:
    """Source PDFs (legacy-seeded and Library-uploaded alike) all live in
    regulation_documents now — prefer the active one for a regulator/
    instrument pair, falling back to the most recent of any status so the
    Library review screen can still preview a not-yet-activated upload."""
    result = await db.execute(
        select(RegulationDocument)
        .where(RegulationDocument.regulator == regulator.upper(), RegulationDocument.instrument == instrument.upper())
        .order_by((RegulationDocument.status == "active").desc(), RegulationDocument.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


@router.get("/classifications", response_model=list[ClassificationResponse])
async def list_classifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    result = await db.execute(
        select(ClassificationJob).order_by(ClassificationJob.created_at.desc()).limit(100)
    )
    return result.scalars().all()


@router.post("/classifications", response_model=ClassificationResponse)
async def create_classification(
    background_tasks: BackgroundTasks,
    vendor_id: uuid.UUID = Form(...),
    text: str = Form(""),
    agent_ids: str = Form(""),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:create")),
):
    assessment_text = text.strip()
    if not assessment_text and not file:
        raise HTTPException(400, "text or file required")

    # Comma-separated agent ids chosen in the UI; empty = built-in default run.
    selected_agent_ids = [a.strip() for a in agent_ids.split(",") if a.strip()]

    settings = get_settings()
    doc_text = ""
    # Whether the upload is already a question/answer grid — see the canonical
    # curation note below. Tracked here because `filename` is scoped to the
    # branch, and relying on `and` short-circuiting to keep it unread is the kind
    # of implicit coupling that breaks the next time this block is reordered.
    doc_is_grid = False
    document_id: uuid.UUID | None = None
    if file:
        data = await file.read()
        filename = file.filename or "upload.txt"
        try:
            doc_text = extract_text(filename, data)
        except ValueError as exc:
            # Unsupported extension. Surfaced rather than swallowed: the old
            # behaviour decoded the bytes as utf-8 and classified the mojibake.
            raise HTTPException(400, str(exc)) from exc
        doc_is_grid = filename.lower().endswith(".xlsx")
        # Persist the original file to object storage and record a Document row so
        # History/Review can show and re-download what the analyst attached.
        vendor = (
            await db.execute(select(Vendor).where(Vendor.id == vendor_id))
        ).scalar_one_or_none()
        doc = Document(
            filename=filename,
            mime_type=file.content_type or "application/octet-stream",
            s3_key="",  # filled below once the row has an id
            size_bytes=len(data),
            extracted_text=doc_text,
            uploaded_by=user.id,
        )
        db.add(doc)
        await db.flush()  # assigns doc.id
        # Human-browsable object key, namespaced by environment so local/dev/uat
        # uploads stay separate in the shared bucket:
        #   <prefix>/<env>/<vendor>_<ts>_<shortid>_<name>.<ext>
        # The short id keeps names unique so same-named uploads never overwrite.
        stem, ext = Path(filename).stem, Path(filename).suffix
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        doc.s3_key = (
            f"{settings.gcs_prefix.strip('/')}/{settings.environment}/"
            f"{_slug(vendor.legal_name if vendor else str(vendor_id))}_"
            f"{ts}_{doc.id.hex[:6]}_{_slug(stem, 'document')}{ext}"
        )
        await get_storage_adapter().upload(doc.s3_key, data, doc.mime_type)
        document_id = doc.id

    # Send the classifier only the curated set of canonical form fields (name,
    # purpose, scope, hosting, DR, nature of info, mode, criteria, ...) with their
    # answers — not the whole form. Falls back to the full text when none of the
    # canonical fields are found (e.g. a non-standard document), so the classifier
    # is never handed an empty payload. The full extracted_text is still stored on
    # the Document row for audit regardless.
    #
    # Spreadsheets skip that curation entirely. It is tuned to the outsourcing
    # form's prose "Label : value" layout, and against a Sl.No/Parameter/Response
    # grid it matches a handful of labels whose values then run on into the next
    # question — on the reference VDD workbook it reduces 9.2k chars of clean rows
    # to four bleeding lines, and because the fallback below is `or doc_text` those
    # four *replace* the good text rather than supplementing it. A grid already
    # reads as "question | answer", so it needs no curation.
    ai_doc_text = doc_text
    if doc_text and not doc_is_grid:
        ai_doc_text = extract_canonical_fields(doc_text) or doc_text
    combined_text = "\n\n--- Document content ---\n".join(p for p in (assessment_text, ai_doc_text) if p)

    svc = ClassificationService(db)
    job = await svc.create_job(vendor_id, combined_text, document_id, user.id, selected_agent_ids)
    # Commit so the row is visible to the background task's own DB session, then
    # run the multi-call Gemini classification off the request path (same in every
    # environment) so a slow run never blocks the response. The frontend polls
    # job status for the result.
    await db.commit()
    background_tasks.add_task(run_classification_bg, str(job.id), str(user.id))
    return job


@router.get("/classifications/ai-status")
async def classification_ai_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ai = AIGateway(db)
    kill = await ai.is_kill_switch_active("M1")
    return {"module": "M1", "kill_switch": kill, "ai_enabled": not kill}


@router.get("/classifications/{job_id}", response_model=ClassificationResponse)
async def get_classification(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    result = await db.execute(select(ClassificationJob).where(ClassificationJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Not found")
    return job


@router.get("/classifications/{job_id}/document")
async def download_classification_document(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    """Stream the original file the analyst attached to this classification."""
    result = await db.execute(select(ClassificationJob).where(ClassificationJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job or not job.document:
        raise HTTPException(404, "No document attached to this classification")
    doc = job.document
    data = await get_storage_adapter().download(doc.s3_key)
    return FastResponse(
        content=data,
        media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.get("/classifications/{job_id}/report.pdf")
async def export_classification_pdf(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    """Downloadable PDF summarising the confirmed classification outcome."""
    svc = ReportingService(db)
    try:
        pdf = await svc.generate_classification_pdf(job_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return FastResponse(content=pdf, media_type="application/pdf")


@router.post("/classifications/{job_id}/confirm", response_model=ClassificationResponse)
async def confirm_classification(
    job_id: uuid.UUID,
    body: ClassificationConfirm,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:approve")),
):
    svc = ClassificationService(db)
    return await svc.confirm(job_id, user.id, body.label, body.source)


@router.post("/classifications/{job_id}/override", response_model=ClassificationResponse)
async def override_classification(
    job_id: uuid.UUID,
    body: ClassificationOverride,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:override")),
):
    svc = ClassificationService(db)
    try:
        job = await svc.override(job_id, user.id, body.label, body.justification)
        # Optional learning loop: fold the reviewer's prompt improvement into an
        # existing agent or a new one. Only runs when a learning was entered.
        if body.learning_info and body.learning_info.strip():
            await AgentService(db).apply_learning(
                learning_info=body.learning_info,
                source=body.source,
                mode=body.learning_mode or "existing",
                target_agent_id=body.target_agent_id,
                base_agent_id=body.base_agent_id,
                new_agent_name=body.new_agent_name,
                actor_id=user.id,
            )
        return job
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/vendors/{vendor_id}/classification", response_model=ClassificationResponse | None)
async def get_vendor_classification(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    svc = ClassificationService(db)
    job = await svc.get_vendor_classification(vendor_id)
    return job


@router.get("/clauses/pdf/annotated")
async def get_annotated_clause_pdf(
    regulator: str,
    instrument: str,
    clause_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    """Return the source PDF with the cited clause highlighted via PyMuPDF annotations.
    Uses the exact clause_id UUID so the page_no and text match what evidence enrichment used.
    Falls back to unannotated PDF if clause not found or annotation fails."""
    import fitz

    clause = None
    try:
        result = await db.execute(
            select(RegulatorClause)
            .where(RegulatorClause.id == uuid.UUID(clause_id))
        )
        clause = result.scalar_one_or_none()
    except Exception:
        pass  # serve PDF without highlights if lookup fails

    # Resolve the exact document the cited clause came from, not just "a"
    # document matching regulator+instrument — if a regulator/instrument
    # ever has more than one document row (e.g. an amended circular
    # uploaded before the old one is archived), the regulator+instrument
    # lookup alone can't tell them apart and could silently show the wrong
    # source PDF for this citation. Only fall back to that heuristic when
    # the clause itself has no document_id (pre-Library legacy rows).
    document = None
    if clause and clause.document_id:
        doc_result = await db.execute(
            select(RegulationDocument).where(RegulationDocument.id == clause.document_id)
        )
        document = doc_result.scalar_one_or_none()
    if not document:
        document = await _find_regulation_document(db, regulator, instrument)
    if not document:
        raise HTTPException(404, f"No PDF registered for {regulator}/{instrument}")

    doc = fitz.open(stream=document.pdf_bytes, filetype="pdf")

    if clause and clause.text:
        page_no: int = clause.page_no or 1
        # Take only the first 3 meaningful lines — enough to pinpoint the clause
        # without over-highlighting sub-items that span pages.
        lines = [ln.strip() for ln in clause.text.split("\n") if len(ln.strip()) > 15][:3]
        try:
            for line in lines:
                for offset in range(3):
                    pg_idx = page_no - 1 + offset
                    if pg_idx >= len(doc):
                        break
                    pg = doc[pg_idx]
                    rects = pg.search_for(line)
                    for rect in rects:
                        # Draw a semi-transparent yellow fill rectangle directly
                        # into the page content stream — no annotation layer,
                        # no popup text, no pdf.js overlay issues.
                        pg.draw_rect(rect, color=None, fill=(1.0, 0.92, 0.23), fill_opacity=0.45)
                    if rects:
                        break
        except Exception:
            pass

    pdf_bytes = doc.tobytes()
    doc.close()

    return FastResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "max-age=300"},
    )


@router.get("/clauses/pdf")
async def get_clause_source_pdf(
    regulator: str,
    instrument: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    """Serve the gazetted source PDF for a regulator/instrument pair, from
    regulation_documents (both legacy-seeded and Library-uploaded PDFs live
    there — see backfill_documents.py for the legacy migration)."""
    document = await _find_regulation_document(db, regulator, instrument)
    if not document:
        raise HTTPException(404, f"No PDF registered for {regulator}/{instrument}")
    return FastResponse(
        content=document.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "Cache-Control": "max-age=3600"},
    )


@router.get("/clauses", response_model=list[ClauseResponse])
async def list_clauses(
    version: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    stmt = select(RegulatorClause)
    if version:
        stmt = stmt.where(RegulatorClause.version == version)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/clauses", response_model=ClauseResponse)
async def create_clause(
    body: ClauseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:clause_edit")),
):
    from datetime import datetime, timezone

    clause = RegulatorClause(
        version=body.version,
        effective_from=datetime.now(timezone.utc),
        regulator=body.regulator,
        clause_ref=body.clause_ref,
        text=body.text,
        tags=body.tags,
        instrument=body.instrument,
        source_doc=body.source_doc,
        page_no=body.page_no,
        para_no=body.para_no,
    )
    db.add(clause)
    await db.flush()
    return clause
