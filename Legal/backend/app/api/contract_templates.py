"""Contract template library — GCS browse/upload + DB templates for MSA start."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.rbac import Permission
from app.database import get_db
from app.models.contract_template import ContractTemplate
from app.models.user import User
from app.schemas.contract_template import (
    ContractTemplateCreate,
    ContractTemplateOut,
    ContractTemplateSummary,
    ContractTemplateUpdate,
    TemplateLibraryCategoriesOut,
    TemplateLibraryItemOut,
    TemplateLibraryPreviewOut,
)
from app.services import template_service
from app.services.document_parser import DocumentParseError, parse_document
from app.services.gcs_template_library import (
    TemplateLibraryError,
    download_library_bytes,
    library_categories,
    list_library,
    preview_library_text,
    upload_library_file,
)

logger = logging.getLogger("legalos.templates")

router = APIRouter(prefix="/api/contract-templates", tags=["contract-templates"])


@router.get("/library/categories", response_model=TemplateLibraryCategoriesOut)
def get_library_categories(
    _: User = Depends(require_permission(Permission.MSA_AUTOMATION)),
) -> TemplateLibraryCategoriesOut:
    return TemplateLibraryCategoriesOut(**library_categories())


@router.get("/library", response_model=list[TemplateLibraryItemOut])
def list_template_library(
    doc_kind: str | None = None,
    contract_type: str | None = None,
    _: User = Depends(require_permission(Permission.MSA_AUTOMATION)),
    db: Session = Depends(get_db),
) -> list[TemplateLibraryItemOut]:
    """List documents from ``gs://legalos/legal_templates`` (configurable)."""
    try:
        items = list_library(doc_kind=doc_kind, contract_type=contract_type)
    except TemplateLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list GCS template library")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not load template library from GCS: {exc}",
        ) from exc

    keys = [i.storage_key for i in items]
    db_by_key: dict[str, int] = {}
    if keys:
        rows = db.execute(
            select(ContractTemplate.id, ContractTemplate.storage_key).where(
                ContractTemplate.storage_key.in_(keys)
            )
        ).all()
        db_by_key = {k: i for i, k in rows if k}

    return [
        TemplateLibraryItemOut(
            name=i.name,
            filename=i.filename,
            doc_kind=i.doc_kind,
            contract_type=i.contract_type,
            description=i.description,
            storage_key=i.storage_key,
            content_type=i.content_type,
            size_bytes=i.size_bytes,
            updated_at=i.updated_at,
            source=i.source,
            db_id=db_by_key.get(i.storage_key),
        )
        for i in items
    ]


@router.get("/library/preview", response_model=TemplateLibraryPreviewOut)
def preview_template_library_file(
    storage_key: str,
    _: User = Depends(
        require_permission(Permission.MSA_AUTOMATION, Permission.LEGAL_BOT_USE)
    ),
) -> TemplateLibraryPreviewOut:
    """Extract and return plain text so users can view the document contents."""
    try:
        payload = preview_library_text(storage_key)
    except TemplateLibraryError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GCS template preview failed key=%s", storage_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not preview document: {exc}",
        ) from exc
    return TemplateLibraryPreviewOut(**payload)


@router.get("/library/file")
def download_template_library_file(
    storage_key: str,
    _: User = Depends(
        require_permission(Permission.MSA_AUTOMATION, Permission.LEGAL_BOT_USE)
    ),
) -> Response:
    """Stream the original library file (PDF/DOCX/TXT) for in-app document viewing."""
    try:
        data, item = download_library_bytes(storage_key)
    except TemplateLibraryError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GCS template download failed key=%s", storage_key)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not download document: {exc}",
        ) from exc

    media = item.content_type or "application/octet-stream"
    filename = item.filename or "document"
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/library/upload", response_model=TemplateLibraryItemOut, status_code=status.HTTP_201_CREATED)
async def upload_template_library_file(
    file: UploadFile = File(...),
    doc_kind: str = Form(...),
    contract_type: str = Form(...),
    name: str | None = Form(None),
    description: str | None = Form(None),
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> TemplateLibraryItemOut:
    """Upload docx/pdf/txt into the GCS template library."""
    data = await file.read()
    filename = file.filename or "document.bin"
    try:
        item = upload_library_file(
            data=data,
            filename=filename,
            doc_kind=doc_kind,
            contract_type=contract_type,
            name=name,
            description=description,
        )
    except TemplateLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GCS template upload failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not upload to GCS: {exc}",
        ) from exc

    db_id: int | None = None
    # Mirror into DB when text can be extracted so MSA start can use it.
    try:
        text = parse_document(data, filename, file.content_type)
    except DocumentParseError:
        text = ""
    if text.strip():
        desc_parts = [p for p in (item.doc_kind, description) if p]
        row = ContractTemplate(
            contract_type=item.contract_type,
            name=item.name,
            description=" · ".join(desc_parts) if desc_parts else description,
            template_text=text[:500_000],
            storage_key=item.storage_key,
            is_active=True,
            created_by_id=user.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        db_id = row.id

    return TemplateLibraryItemOut(
        name=item.name,
        filename=item.filename,
        doc_kind=item.doc_kind,
        contract_type=item.contract_type,
        description=item.description,
        storage_key=item.storage_key,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        updated_at=item.updated_at,
        source=item.source,
        db_id=db_id,
    )


@router.get("", response_model=list[ContractTemplateSummary])
def list_templates(
    contract_type: str | None = None,
    _: User = Depends(require_permission(Permission.MSA_AUTOMATION)),
    db: Session = Depends(get_db),
) -> list[ContractTemplateSummary]:
    rows = template_service.list_templates(db, contract_type=contract_type)
    return [ContractTemplateSummary.model_validate(t) for t in rows]


@router.get("/{template_id}", response_model=ContractTemplateOut)
def get_template(
    template_id: int,
    _: User = Depends(require_permission(Permission.MSA_AUTOMATION)),
    db: Session = Depends(get_db),
) -> ContractTemplateOut:
    t = template_service.get_template(db, template_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return ContractTemplateOut.model_validate(t)


@router.post("", response_model=ContractTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: ContractTemplateCreate,
    user: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> ContractTemplateOut:
    t = ContractTemplate(
        contract_type=payload.contract_type,
        name=payload.name,
        description=payload.description,
        template_text=payload.template_text,
        is_active=payload.is_active,
        created_by_id=user.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return ContractTemplateOut.model_validate(t)


@router.patch("/{template_id}", response_model=ContractTemplateOut)
def update_template(
    template_id: int,
    payload: ContractTemplateUpdate,
    _: User = Depends(require_permission(Permission.PLAYBOOK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> ContractTemplateOut:
    t = template_service.get_template(db, template_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    t.version += 1
    db.commit()
    db.refresh(t)
    return ContractTemplateOut.model_validate(t)
