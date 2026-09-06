"""BannerImageMessage — one turn in the Designer's chat with a hero image.

The Designer can refine a hero image conversationally: each comment is sent to
Nano Banana together with the *current* PNG, which edits that image in place
(same subject and composition, just the requested change) rather than rolling a
fresh one. Every turn is stored here with the resulting PNG snapshot, so the
thread is a scroll-back history of versions. The very first row of a thread is
the base image itself (``comment`` is NULL); regenerating from scratch resets
the thread back to a single base row.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BannerImageMessage(Base):
    """One version of a hero image — the comment that produced it and its bytes."""

    __tablename__ = "banner_image_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("banner_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The Designer's instruction for this turn. NULL on the base/seed version.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)  # the full prompt sent
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # this version's PNG
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    image: Mapped["BannerImage"] = relationship(  # noqa: F821
        back_populates="messages",
        foreign_keys=[image_id],
    )
