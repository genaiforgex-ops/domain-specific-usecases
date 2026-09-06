"""ImagePrompt — a user's custom hero-image art-direction for one banner template.

Prompt management (the "Prompt Studio"): each banner template is an image
use-case (e.g. performance statics vs WhatsApp/RCS/RPN messaging), and a user can
override that template's default art-direction (`BannerTemplate.image_brief`) with
their own. Overrides are per-user and per-template — one row per (user, template).
When a user generates images with a template, the enabled override wins; otherwise
the template default applies.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImagePrompt(Base):
    __tablename__ = "image_prompts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banner_templates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The user's art-direction override for this template's hero photos.
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # A user can keep an override on file but toggle it off (falls back to default).
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
