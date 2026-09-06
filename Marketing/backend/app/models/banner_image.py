"""BannerImage model — the AI-generated hero imagery for a creative.

Once a brief reaches the Designer (stage = design), the Designer generates a
hero image per creative with Nano Banana (the Gemini image model), reviews them,
and approves the set. Approved images are uploaded into a fresh Figma file and
used as the hero photo in every ad size for that creative.

One row per creative holds the *current* image (regenerating replaces the bytes
in place). The PNG bytes live in the row so the flow needs no media volume; they
are served back to the browser through a dedicated content endpoint.
"""

from datetime import datetime
from enum import Enum

import uuid

from sqlalchemy import (
    UUID,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BannerImageStatus(str, Enum):
    pending = "pending"  # generated, awaiting the Designer's review
    approved = "approved"  # the Designer signed off — eligible for Figma export


class BannerImage(Base):
    """The current AI hero image for one creative."""

    __tablename__ = "banner_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creatives.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    prompt: Mapped[str] = mapped_column(Text, nullable=False)  # the image prompt used
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # the PNG bytes

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BannerImageStatus.pending.value
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    # The version the Designer has chosen as current — what the card, the approval
    # gate and the Figma export all use. `data` mirrors this version's bytes. NULL
    # only for legacy images generated before the chat thread existed.
    active_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banner_image_messages.id", use_alter=True, ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creative: Mapped["Creative"] = relationship(back_populates="banner_image")  # noqa: F821
    # The Designer's chat thread for this image — base version first, then each edit.
    messages: Mapped[list["BannerImageMessage"]] = relationship(  # noqa: F821
        back_populates="image",
        cascade="all, delete-orphan",
        order_by="BannerImageMessage.created_at, BannerImageMessage.id",
        foreign_keys="BannerImageMessage.image_id",
    )
    # The currently-selected version. post_update breaks the image⇆message FK cycle
    # on flush (insert both, then UPDATE the pointer).
    active_message: Mapped["BannerImageMessage | None"] = relationship(  # noqa: F821
        foreign_keys=[active_message_id],
        post_update=True,
    )
