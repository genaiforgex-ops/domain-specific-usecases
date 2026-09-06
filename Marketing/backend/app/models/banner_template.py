"""BannerTemplate — a reusable, on-brand banner design stored in the DB.

A template bundles everything the Figma export needs to render creatives: the
Plugin-API render program (`js_body`), the brand system (`brand`), the ad sizes
(`sizes`), the per-size brand-strip SVGs (`strips`, keyed by size name), and the
default footer lines. Templates are global (shared brand assets, not per-user);
the export picks the `is_default` row unless a specific one is chosen. Seeded with
the built-in performance template (see the banner_templates migration); more rows will
back a template gallery later.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, DateTime, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BannerTemplate(Base):
    __tablename__ = "banner_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    # The template family the Product Lead picks at brief creation (e.g.
    # "performance" statics vs "messaging" WhatsApp/RCS/RPN). Many templates can
    # share a category; the Designer picks a specific one within the brief's category.
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="performance")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The Figma Plugin-API render program run by use_figma (the FIGMA_JS_BODY).
    js_body: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[dict] = mapped_column(JSONB, nullable=False)  # BRAND system dict
    sizes: Mapped[list] = mapped_column(JSONB, nullable=False)  # list of {name,w,h,pos}
    footer_left: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    footer_right: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Hero-photo art-direction fed to the image model so the generated subject leaves
    # this template's copy area clear (e.g. messaging: subject left, copy right).
    image_brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Image model output shape/resolution for this format's heroes. `image_aspect`
    # is a Gemini aspect ratio ("1:1", "16:9", …); `image_size` is a tier ("1K",
    # "2K", "4K"). Empty = let the model default. Set as real params, not prompt text.
    image_aspect: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    image_size: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    # Shrunk brand-strip SVGs keyed by size name; sizes absent here fall back to
    # the generated dot ribbon in js_body.
    strips: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The reference artwork the Designer picks from: a rendered sample of what this
    # template looks like. Stored as bytes in the row (like banner_images) so the
    # gallery needs no media volume — the browser fetches it from a content
    # endpoint. NULL until an Admin uploads one; the picker then falls back to a
    # text-only card.
    preview_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    preview_mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The one template the export uses when none is chosen.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Seeded brand template — kept distinct so the gallery can protect it later.
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
