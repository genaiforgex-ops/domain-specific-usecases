"""DesignPrompt — a user's override of the shared hero-image "design prompt" base.

The Prompt Studio's design-base setting: one row per user holding a replacement for
the built-in brand scaffold (photography rules + text-free/full-bleed constraints +
quality bar). When enabled, it replaces the default base at generation time; the
per-creative scene and per-format composition are still appended on top (see
banner_image_service._image_prompt). Unlike ImagePrompt (per template), this is a
single per-user value shared across every format.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DesignPrompt(Base):
    __tablename__ = "design_prompts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # The user's replacement for the built-in design-prompt base.
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # A user can keep an override on file but toggle it off (falls back to default).
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
