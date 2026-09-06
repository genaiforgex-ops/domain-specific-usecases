"""BriefEvent — the append-only audit trail of everything that happens to a brief.

Every meaningful state change (created, submitted, approved, changes requested)
writes one row here. Rows are never edited or deleted, so the trail is immutable
and identity-stamped. Actor name/role are denormalised onto the row so the audit
log reads correctly even if a user is later renamed or removed.
"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import UUID, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BriefEventKind(str, Enum):
    created = "created"
    edited = "edited"  # the author (or reviewing Marketing Lead) saved a content change
    deleted = "deleted"  # a draft/returned brief was discarded (soft-deleted)
    reference_added = "reference_added"  # a sample/example image was attached to the brief
    reference_removed = "reference_removed"  # a sample/example image was removed
    submitted = "submitted"
    approved = "approved"
    changes_requested = "changes_requested"
    assigned = "assigned"  # routed to the Copywriter on submit
    creatives_generated = "creatives_generated"  # Copy Agent produced the copies
    copies_submitted = "copies_submitted"  # Copywriter sent the copies for approval
    gate1_signoff = "gate1_signoff"  # an approval checkpoint was decided
    gate1_cleared = "gate1_cleared"  # final sign-off complete — pipeline done
    banner_template_selected = "banner_template_selected"  # Designer chose the template
    banner_images_generated = "banner_images_generated"  # Designer ran Nano Banana
    banner_image_uploaded = "banner_image_uploaded"  # Designer swapped in their own image
    banner_image_edited = "banner_image_edited"  # Designer hand-edited one in the Design Studio
    banner_images_approved = "banner_images_approved"  # Designer approved the hero images
    design_submitted = "design_submitted"  # Designer sent the design for creative review
    figma_exported = "figma_exported"  # Designer exported the banners to a Figma file


class BriefEvent(Base):
    """One immutable entry in a brief's history."""

    __tablename__ = "brief_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # BriefEventKind
    action: Mapped[str] = mapped_column(String(255), nullable=False)  # human phrase

    # Denormalised actor identity — stable even if the user record changes.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(8), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brief: Mapped["Brief"] = relationship(back_populates="events")  # noqa: F821
