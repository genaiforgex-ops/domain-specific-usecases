"""Prompt Studio — per-user hero-image art-direction, one setting per banner template.

Each banner template is an image use-case (performance statics, WhatsApp/RCS/RPN
messaging, …) with a built-in default art-direction (`BannerTemplate.image_brief`).
A user can override that default with their own text; overrides are per-user and
stored one row per (user, template). `resolve_brief` is the hot path the image
generator calls to get the effective art-direction for a user + template.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.banner_template import BannerTemplate
from app.models.image_prompt import ImagePrompt
from app.services import banner_template_service


@dataclass(frozen=True)
class EffectivePrompt:
    """A template's image use-case as the current user sees it: the built-in default,
    the user's override (if any), and which one is in effect."""

    template: BannerTemplate
    default_prompt: str
    override: ImagePrompt | None

    @property
    def is_custom(self) -> bool:
        return self.override is not None

    @property
    def enabled(self) -> bool:
        return self.override.enabled if self.override else False

    @property
    def prompt(self) -> str:
        """What the user currently sees in the editor — their override text if they
        have one, otherwise the built-in default (a starting point to edit)."""
        return self.override.prompt if self.override else self.default_prompt

    @property
    def effective_prompt(self) -> str:
        """What generation actually uses — the enabled override, else the default."""
        if self.override and self.override.enabled and self.override.prompt.strip():
            return self.override.prompt
        return self.default_prompt


def _get(db: Session, user_id: uuid.UUID, template_id: uuid.UUID) -> ImagePrompt | None:
    return db.get(ImagePrompt, {"user_id": user_id, "template_id": template_id})


def list_effective(db: Session, user_id: uuid.UUID) -> list[EffectivePrompt]:
    """One entry per banner template (the image use-cases), default first, with the
    user's override folded in — powers the Prompt Studio."""
    templates = banner_template_service.list_templates(db)
    overrides = {
        o.template_id: o
        for o in db.scalars(select(ImagePrompt).where(ImagePrompt.user_id == user_id))
    }
    return [
        EffectivePrompt(
            template=t,
            default_prompt=t.image_brief or "",
            override=overrides.get(t.id),
        )
        for t in templates
    ]


def get_effective(
    db: Session, user_id: uuid.UUID, template_id: uuid.UUID
) -> EffectivePrompt | None:
    t = banner_template_service.get(db, template_id)
    if t is None:
        return None
    return EffectivePrompt(
        template=t,
        default_prompt=t.image_brief or "",
        override=_get(db, user_id, template_id),
    )


def set_prompt(
    db: Session, user_id: uuid.UUID, template_id: uuid.UUID, prompt: str, enabled: bool
) -> EffectivePrompt:
    """Create or update the user's art-direction override for a template."""
    t = banner_template_service.get(db, template_id)
    if t is None:
        raise ValueError("Banner template not found")
    row = _get(db, user_id, template_id)
    if row is None:
        row = ImagePrompt(user_id=user_id, template_id=template_id)
        db.add(row)
    row.prompt = prompt
    row.enabled = enabled
    db.commit()
    db.refresh(t)
    return EffectivePrompt(template=t, default_prompt=t.image_brief or "", override=row)


def reset(db: Session, user_id: uuid.UUID, template_id: uuid.UUID) -> EffectivePrompt:
    """Drop the user's override so the template default applies again."""
    t = banner_template_service.get(db, template_id)
    if t is None:
        raise ValueError("Banner template not found")
    row = _get(db, user_id, template_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return EffectivePrompt(template=t, default_prompt=t.image_brief or "", override=None)


def resolve_brief(
    db: Session, user_id: uuid.UUID, template: BannerTemplate | None, default_brief: str
) -> str:
    """The art-direction to use when generating for `user_id` with `template`: the
    user's enabled override, else the template's built-in default. `default_brief`
    is the resolved bundle brief (covers the built-in-fallback case where there is
    no template row to attach an override to)."""
    if template is None:
        return default_brief
    row = _get(db, user_id, template.id)
    if row is not None and row.enabled and row.prompt.strip():
        return row.prompt
    return default_brief
