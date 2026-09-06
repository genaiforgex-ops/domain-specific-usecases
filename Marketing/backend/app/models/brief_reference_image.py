"""BriefReferenceImage — sample copies / examples the Product Lead attaches to a
brief so everyone down the chain can see the visual references it's built against.

The Product Lead (or the Marketing Lead while reviewing) uploads example images in
the brief's "Samples / Examples / References" area. They're shown alongside the
brief everywhere it's read, and fed to the Designer's hero-image generation as
visual references. Bytes live in the row (normalised to PNG) so the flow needs no
media volume — served back to the browser through a dedicated content endpoint,
exactly like the Designer's banner images.
"""

import uuid
from datetime import datetime

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


class BriefReferenceImage(Base):
    """One reference image attached to a brief (PNG bytes stored in the row)."""

    __tablename__ = "brief_reference_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("briefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # the PNG bytes

    # Who attached it — denormalised name kept so the read view can credit the
    # uploader even if the account is later removed.
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brief: Mapped["Brief"] = relationship(back_populates="reference_images")  # noqa: F821
