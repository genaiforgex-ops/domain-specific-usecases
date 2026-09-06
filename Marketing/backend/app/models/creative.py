"""Creative model — the structured ad creatives generated from a brief.

Once a brief clears Gate 1, the Creative Agent turns its authorized creative
prompt and context into a set of ready-to-produce creatives. Each row is one
creative in the standard format: a headline, body copy, CTA, entity attribution,
and the mandatory terms line, plus a visual reference describing the art."""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Creative(Base):
    """One generated ad creative belonging to a brief."""

    __tablename__ = "creatives"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # display order

    visual_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(120), nullable=False)
    # Attribution and terms are free-form AI output (terms can be a full legal
    # disclaimer), so they're unbounded rather than capped VARCHARs.
    entity_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")

    # The version whose copy is mirrored onto the fields above — what approvals and
    # the Figma export read. NULL only for creatives that predate versioning.
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creative_versions.id", use_alter=True, ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brief: Mapped["Brief"] = relationship(back_populates="creatives")  # noqa: F821
    # The Designer's AI hero image for this creative (one current image, replaced
    # on regenerate). Present only once the brief reaches the Designer.
    banner_image: Mapped["BannerImage | None"] = relationship(  # noqa: F821
        back_populates="creative",
        cascade="all, delete-orphan",
        uselist=False,
    )
    # Version history — the generated base first, then each manual edit.
    versions: Mapped[list["CreativeVersion"]] = relationship(  # noqa: F821
        back_populates="creative",
        cascade="all, delete-orphan",
        order_by="CreativeVersion.created_at, CreativeVersion.id",
        foreign_keys="CreativeVersion.creative_id",
    )
    # The currently-selected version. post_update breaks the creative⇆version FK
    # cycle on flush (insert both, then UPDATE the pointer).
    active_version: Mapped["CreativeVersion | None"] = relationship(  # noqa: F821
        foreign_keys=[active_version_id],
        post_update=True,
    )
