"""Banner-template gallery routes.

Lists the shared, on-brand banner templates (optionally within one category) and
returns one template's preview details, plus the reference artwork the Designer
picks a template by — served from the DB and uploaded by an Admin. The Figma
export picks the default template (or a chosen one) server-side via
banner_template_service; create/update/delete will land with the gallery UI.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.database import get_db
from app.models.banner_template import BannerTemplate
from app.models.user import User
from app.schemas.banner_template import BannerTemplateDetail, BannerTemplateSummary
from app.services import banner_template_service
from app.services.figma import render

router = APIRouter(prefix="/api/banner-templates", tags=["banner-templates"])


def _size_names(t: BannerTemplate) -> list[str]:
    return [s.get("name", "") for s in (t.sizes or [])]


def _summary(t: BannerTemplate) -> BannerTemplateSummary:
    return BannerTemplateSummary(
        id=t.id,
        name=t.name,
        category=t.category,
        description=t.description,
        is_default=t.is_default,
        is_builtin=t.is_builtin,
        size_names=_size_names(t),
        has_preview=t.preview_image is not None,
        updated_at=t.updated_at,
        created_at=t.created_at,
    )


def _detail(t: BannerTemplate) -> BannerTemplateDetail:
    return BannerTemplateDetail(
        **_summary(t).model_dump(),
        brand=t.brand,
        sizes=t.sizes,
        footer_left=t.footer_left,
        footer_right=t.footer_right,
        hero_guides=render.hero_guides_for(t.brand or {}, t.sizes or []),
    )


@router.get("", response_model=list[BannerTemplateSummary])
def list_banner_templates(
    category: str | None = None,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BannerTemplateSummary]:
    """The gallery. `category` narrows it to one family — the Designer's picker asks
    for the category the Product Lead locked on the brief."""
    return [_summary(t) for t in banner_template_service.list_templates(db, category)]


@router.get("/default", response_model=BannerTemplateDetail)
def get_default_banner_template(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerTemplateDetail:
    """The template the export uses when none is chosen — powers the size picker."""
    t = banner_template_service.get_default(db)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No banner template exists yet")
    return _detail(t)


@router.get("/{template_id}", response_model=BannerTemplateDetail)
def get_banner_template(
    template_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BannerTemplateDetail:
    t = banner_template_service.get(db, template_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Banner template not found")
    return _detail(t)


def _template_or_404(db: Session, template_id: uuid.UUID) -> BannerTemplate:
    t = banner_template_service.get(db, template_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Banner template not found")
    return t


@router.get("/{template_id}/preview")
def banner_template_preview(
    template_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """The template's reference artwork — the image the Designer picks the template
    by. 404 when none is uploaded yet (the card falls back to name + sizes)."""
    t = _template_or_404(db, template_id)
    if not t.preview_image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This template has no preview image"
        )
    return Response(content=t.preview_image, media_type=t.preview_mime or "image/png")


@router.post("/{template_id}/preview", response_model=BannerTemplateSummary)
async def upload_banner_template_preview(
    template_id: uuid.UUID,
    file: UploadFile = File(...),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BannerTemplateSummary:
    """Attach a template's reference artwork (Admin only) — how the sample banner
    images for a category get into the DB, so the Designer's picker is visual."""
    t = _template_or_404(db, template_id)
    data = await file.read()
    try:
        banner_template_service.set_preview(db, t, data, file.content_type or "")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _summary(t)


@router.delete("/{template_id}/preview", response_model=BannerTemplateSummary)
def delete_banner_template_preview(
    template_id: uuid.UUID,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> BannerTemplateSummary:
    """Remove a template's reference artwork (Admin only)."""
    t = _template_or_404(db, template_id)
    banner_template_service.clear_preview(db, t)
    return _summary(t)
