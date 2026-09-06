"""Banner templates — the DB-backed gallery of on-brand banner designs.

Templates are global (shared brand assets, not per-user). `resolve_bundle` is the
hot path the Figma export calls to get the render inputs for a chosen (or the
default) template; `list_templates` / `get` back the read-only gallery API. If no
template row exists yet (e.g. the seed migration hasn't run on a dev DB), the
export falls back to the built-in performance definition so it never breaks.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.banner_template import BannerTemplate
from app.services.figma import render


def _to_bundle(t: BannerTemplate) -> render.TemplateBundle:
    return render.TemplateBundle(
        brand=t.brand,
        sizes=t.sizes,
        js_body=t.js_body,
        strips=t.strips or {},
        footer_left=t.footer_left,
        footer_right=t.footer_right,
        image_brief=t.image_brief or "",
        image_aspect=t.image_aspect or "",
        image_size=t.image_size or "",
    )


def list_templates(db: Session, category: str | None = None) -> list[BannerTemplate]:
    """Templates, default first, then newest — the gallery order. `category` narrows
    to one family (what the Designer may pick from, per the brief's locked category)."""
    stmt = select(BannerTemplate)
    if category:
        stmt = stmt.where(BannerTemplate.category == category)
    return list(
        db.scalars(
            stmt.order_by(BannerTemplate.is_default.desc(), BannerTemplate.created_at.desc())
        )
    )


def get(db: Session, template_id: uuid.UUID) -> BannerTemplate | None:
    return db.get(BannerTemplate, template_id)


def get_default(db: Session) -> BannerTemplate | None:
    """The template the export uses when none is chosen: the `is_default` row, or
    the oldest row if none is flagged."""
    row = db.scalars(
        select(BannerTemplate).where(BannerTemplate.is_default.is_(True)).limit(1)
    ).first()
    if row is not None:
        return row
    return db.scalars(
        select(BannerTemplate).order_by(BannerTemplate.created_at.asc()).limit(1)
    ).first()


ALLOWED_PREVIEW_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_PREVIEW_BYTES = 10 * 1024 * 1024  # a rendered banner sample, not a print master


def set_preview(
    db: Session, template: BannerTemplate, data: bytes, mime_type: str
) -> BannerTemplate:
    """Attach the template's reference artwork — the image the Designer picks by."""
    if mime_type not in ALLOWED_PREVIEW_TYPES:
        raise ValueError("Unsupported image type — use PNG, JPEG or WEBP")
    if not data:
        raise ValueError("Uploaded file is empty")
    if len(data) > MAX_PREVIEW_BYTES:
        raise ValueError("Uploaded file is too large (max 10 MB)")
    template.preview_image = data
    template.preview_mime = mime_type
    db.commit()
    db.refresh(template)
    return template


def clear_preview(db: Session, template: BannerTemplate) -> BannerTemplate:
    """Drop the reference artwork — the card falls back to name + sizes."""
    template.preview_image = None
    template.preview_mime = None
    db.commit()
    db.refresh(template)
    return template


def resolve_bundle(
    db: Session, template_id: uuid.UUID | None = None
) -> tuple[BannerTemplate | None, render.TemplateBundle]:
    """Return (row, bundle) for the chosen template, the default when `template_id`
    is None, or (None, built-in bundle) if the table is empty. Raises ValueError
    if a specific `template_id` is given but does not exist."""
    if template_id is not None:
        row = get(db, template_id)
        if row is None:
            raise ValueError("Banner template not found")
        return row, _to_bundle(row)
    row = get_default(db)
    if row is None:
        return None, render.builtin_bundle()
    return row, _to_bundle(row)
