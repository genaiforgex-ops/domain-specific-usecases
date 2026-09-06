"""Schemas for the banner-template gallery (read-only for now).

The heavy fields — the render program (`js_body`) and the per-size strip SVGs —
are never serialised to the client; the gallery only needs identity, the brand
system, the ad sizes and the footer defaults to preview a template.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BannerSize(BaseModel):
    name: str
    w: int
    h: int
    pos: str


class BannerTemplateSummary(BaseModel):
    """Gallery card: identity + which sizes it renders."""

    id: UUID
    name: str
    category: str  # template family (e.g. "performance", "messaging")
    description: str
    is_default: bool
    is_builtin: bool
    size_names: list[str]
    # True when the template has reference artwork uploaded — the picker then shows
    # the image (fetched from the preview endpoint) instead of a text-only card.
    has_preview: bool
    updated_at: datetime
    created_at: datetime


class BannerTemplateDetail(BannerTemplateSummary):
    """Full preview payload — adds the brand system, sizes and footer defaults."""

    brand: dict
    sizes: list[BannerSize]
    footer_left: str
    footer_right: str
    # How this template crops the hero photo, and (when copy sits over the photo)
    # where the copy column lands — drives the Design Studio's crop guides. Derived
    # from the render program's layout constants; see render.hero_guides_for.
    hero_guides: dict
