"""CreativeVersion — one saved version of a creative's copy.

The copywriter's counterpart to BannerImageMessage. Each creative keeps its
*current* copy on the Creative row (so approvals and the Figma export read one
place), while every generation and manual edit is snapshotted here. The thread
is the version history: the first row is the generated base, each later row an
edit. `Creative.active_version_id` points at whichever version is live.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CreativeVersion(Base):
    """One version of a creative — a full copy snapshot and who produced it."""

    __tablename__ = "creative_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creatives.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # How this version came to be — "Generated" for the AI base, "Edited" for a
    # copywriter's manual save. Shown in the version list.
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="Edited")

    # Full copy snapshot (mirrors the editable Creative fields).
    visual_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Denormalised author identity — stable even if the user record changes.
    editor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    editor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creative: Mapped["Creative"] = relationship(  # noqa: F821
        back_populates="versions",
        foreign_keys=[creative_id],
    )
