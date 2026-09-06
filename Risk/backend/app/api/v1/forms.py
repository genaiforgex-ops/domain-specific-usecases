import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response as FastResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import Role, get_current_user, require_permission
from app.models.user import User
from app.schemas.form import (
    ExcelImportPreviewResponse,
    ExcelSheetPreview,
    FormAssignmentBulkCreate,
    FormAssignmentCreate,
    FormAssignmentDraftUpdate,
    FormAssignmentResponse,
    FormAssignmentSubmit,
    FormImportResultResponse,
    FormTemplateCreate,
    FormTemplateResponse,
    FormTemplateUpdate,
)
from app.services.form_export import build_assignment_workbook, merge_answers, parse_answer_workbook
from app.services.form_import import list_workbook_sheets, parse_vdd_sheet
from app.services.form_service import FormService
from app.workers.tasks import run_classification_bg

router = APIRouter(prefix="/forms", tags=["forms"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _assignment_response(a) -> FormAssignmentResponse:
    data = FormAssignmentResponse.model_validate(a)
    vendor = getattr(a, "_vendor", None)
    assignee = getattr(a, "_assignee", None)
    if vendor:
        data.vendor_legal_name = vendor.legal_name
    if assignee:
        data.assignee_display_name = assignee.display_name or assignee.email
    data.classification_status = getattr(a, "_classification_status", None)
    data.classification_label = getattr(a, "_classification_label", None)
    return data


def _template_response(t) -> FormTemplateResponse:
    return FormTemplateResponse.model_validate(t)


def _is_admin(user: User) -> bool:
    return any(r.role == Role.ADMIN.value for r in user.roles)


async def _get_assignment_or_404(db: AsyncSession, assignment_id: uuid.UUID):
    svc = FormService(db)
    assignment = await svc.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    return assignment


async def _get_own_assignment_or_404(db: AsyncSession, assignment_id: uuid.UUID, user: User):
    """Fetch an assignment the caller is allowed to see: theirs, or any if admin."""
    assignment = await _get_assignment_or_404(db, assignment_id)
    if not _is_admin(user) and assignment.assignee_id != user.id:
        raise HTTPException(403, "Not your assignment")
    return assignment


def _slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")[:limit] or "form"


@router.get("/templates", response_model=list[FormTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    templates = await FormService(db).list_templates()
    return [_template_response(t) for t in templates]


@router.post("/templates", response_model=FormTemplateResponse, status_code=201)
async def create_template(
    body: FormTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    template = await FormService(db).create_template(
        body.name, body.schema.model_dump(), user.id
    )
    await db.commit()
    return _template_response(template)


@router.get("/templates/{template_id}", response_model=FormTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    template = await FormService(db).get_template(template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return _template_response(template)


@router.patch("/templates/{template_id}", response_model=FormTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    body: FormTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    svc = FormService(db)
    template = await svc.get_template(template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    schema = body.schema.model_dump() if body.schema else None
    template = await svc.update_template(template, name=body.name, schema=schema, is_active=body.is_active)
    await db.commit()
    return _template_response(template)


@router.post("/templates/import-excel/preview", response_model=ExcelImportPreviewResponse)
async def preview_excel_import(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("forms:manage")),
):
    data = await file.read()
    sheets = list_workbook_sheets(data)
    return ExcelImportPreviewResponse(
        sheets=[ExcelSheetPreview(**s) for s in sheets]
    )


@router.post("/templates/import-excel", response_model=FormTemplateResponse, status_code=201)
async def import_excel_template(
    file: UploadFile = File(...),
    sheet_index: int = 1,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    data = await file.read()
    try:
        parsed = parse_vdd_sheet(
            data,
            sheet_index=sheet_index,
            template_name=file.filename or "Vendor Due Diligence Assessment",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    template = await FormService(db).create_template(parsed["name"], parsed["schema"], user.id)
    await db.commit()
    return _template_response(template)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    try:
        await FormService(db).delete_template(template_id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:assign")),
):
    try:
        await FormService(db).delete_assignment(assignment_id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/assignments", response_model=FormAssignmentResponse, status_code=201)
async def create_assignment(
    body: FormAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:assign")),
):
    try:
        assignment = await FormService(db).create_assignment(
            template_id=body.template_id,
            assignee_id=body.assignee_id,
            assigned_by_id=user.id,
            title=body.title,
            due_at=body.due_at,
            vendor_id=body.vendor_id,
            vendor_name=body.vendor_name,
        )
        await db.commit()
        assignment = await FormService(db).get_assignment(assignment.id)
        return _assignment_response(assignment)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/assignments/bulk", response_model=list[FormAssignmentResponse], status_code=201)
async def create_assignments_bulk(
    body: FormAssignmentBulkCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:assign")),
):
    if not body.assignments:
        raise HTTPException(400, "At least one assignment is required")
    try:
        assignments = await FormService(db).create_assignments_bulk(
            template_id=body.template_id,
            assigned_by_id=user.id,
            title=body.title,
            due_at=body.due_at,
            items=body.assignments,
        )
        await db.commit()
        svc = FormService(db)
        results = []
        for a in assignments:
            loaded = await svc.get_assignment(a.id)
            if loaded:
                results.append(_assignment_response(loaded))
        return results
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/assignments", response_model=list[FormAssignmentResponse])
async def list_assignments(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:manage")),
):
    assignments = await FormService(db).list_assignments()
    return [_assignment_response(a) for a in assignments]


@router.get("/assignments/mine", response_model=list[FormAssignmentResponse])
async def list_my_assignments(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:read")),
):
    assignments = await FormService(db).list_assignments(assignee_id=user.id)
    return [_assignment_response(a) for a in assignments]


@router.get("/assignments/{assignment_id}", response_model=FormAssignmentResponse)
async def get_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assignment = await _get_own_assignment_or_404(db, assignment_id, user)
    return _assignment_response(assignment)


@router.get("/assignments/{assignment_id}/export.xlsx")
async def export_assignment_excel(
    assignment_id: uuid.UUID,
    blank: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download the form as a fillable workbook.

    This is how a form leaves GenAIForge Risk: the assignee sends the file to the vendor,
    who fills it offline and sends it back for import. `blank=true` strips the
    answers so a vendor is not shown a colleague's working notes; otherwise the
    file carries whatever is currently saved — the submitted answers once the
    assignment is locked, the draft before that.
    """
    assignment = await _get_own_assignment_or_404(db, assignment_id, user)
    if not assignment.template:
        raise HTTPException(400, "Assignment has no template")

    if blank:
        answers: dict = {}
    elif assignment.status == "submitted" and assignment.submission:
        answers = assignment.submission.answers or {}
    else:
        answers = assignment.draft_answers or {}

    vendor = getattr(assignment, "_vendor", None)
    content = build_assignment_workbook(
        assignment.template.schema,
        answers,
        {
            "title": assignment.title,
            "vendor_legal_name": vendor.legal_name if vendor else None,
            "assignment_id": str(assignment.id),
            "template_id": str(assignment.template_id),
            "template_version": assignment.template.version,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )

    parts = [_slug(vendor.legal_name) if vendor else None, _slug(assignment.title)]
    parts.append("blank" if blank else assignment.status)
    filename = "_".join(p for p in parts if p) + ".xlsx"
    return FastResponse(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/assignments/{assignment_id}/import-excel", response_model=FormImportResultResponse)
async def import_assignment_excel(
    assignment_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:fill")),
):
    """Load a vendor-filled workbook back into the draft.

    Imported answers win over what is already in the draft. Blank cells are
    dropped by the parser rather than sent as "", so a question the vendor left
    untouched keeps the answer already saved here.
    """
    assignment = await _get_assignment_or_404(db, assignment_id)
    if assignment.assignee_id != user.id:
        raise HTTPException(403, "Not your assignment")
    if assignment.status == "submitted":
        raise HTTPException(400, "Assignment already submitted")
    if not assignment.template:
        raise HTTPException(400, "Assignment has no template")

    data = await file.read()
    try:
        parsed = parse_answer_workbook(data, assignment.template.schema)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    file_template_id = parsed.meta.get("template_id")
    if file_template_id and file_template_id != str(assignment.template_id):
        raise HTTPException(400, "This file was exported from a different form template")
    file_assignment_id = parsed.meta.get("assignment_id")
    if file_assignment_id and file_assignment_id != str(assignment.id):
        # Same template, different assignment — legitimate (reusing a vendor's
        # answers across forms), so warn rather than block.
        parsed.warnings.append("This file was exported from a different assignment of the same form.")

    if not parsed.answers:
        raise HTTPException(400, "No answers were found in that file")

    svc = FormService(db)
    merged = merge_answers(assignment.draft_answers, parsed.answers)
    try:
        assignment = await svc.save_draft(assignment, merged)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await svc.audit.log(
        event_type="form.imported",
        entity_type="form_assignment",
        entity_id=str(assignment.id),
        actor_id=user.id,
        payload={
            "filename": file.filename,
            "imported_count": len(parsed.answers),
            "unmatched_count": len(parsed.unmatched),
        },
    )
    await db.commit()

    assignment = await FormService(db).get_assignment(assignment.id)
    return FormImportResultResponse(
        assignment=_assignment_response(assignment),
        imported_count=len(parsed.answers),
        unmatched=parsed.unmatched[:20],
        warnings=parsed.warnings,
    )


@router.patch("/assignments/{assignment_id}", response_model=FormAssignmentResponse)
async def save_draft(
    assignment_id: uuid.UUID,
    body: FormAssignmentDraftUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:fill")),
):
    assignment = await _get_assignment_or_404(db, assignment_id)
    if assignment.assignee_id != user.id:
        raise HTTPException(403, "Not your assignment")
    try:
        assignment = await FormService(db).save_draft(assignment, body.answers)
        await db.commit()
        assignment = await FormService(db).get_assignment(assignment.id)
        return _assignment_response(assignment)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/assignments/{assignment_id}/submit", response_model=FormAssignmentResponse)
async def submit_assignment(
    assignment_id: uuid.UUID,
    body: FormAssignmentSubmit,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:submit")),
):
    assignment = await _get_assignment_or_404(db, assignment_id)
    if assignment.assignee_id != user.id:
        raise HTTPException(403, "Not your assignment")
    try:
        _, job_id = await FormService(db).submit_assignment(assignment, body.answers, user.id)
        await db.commit()
        background_tasks.add_task(run_classification_bg, str(job_id), str(user.id))
        assignment = await FormService(db).get_assignment(assignment.id)
        return _assignment_response(assignment)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/assignments/{assignment_id}/remind", response_model=FormAssignmentResponse)
async def remind_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("forms:assign")),
):
    assignment = await _get_assignment_or_404(db, assignment_id)
    try:
        await FormService(db).send_reminder(assignment)
        await db.commit()
        assignment = await FormService(db).get_assignment(assignment.id)
        return _assignment_response(assignment)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
