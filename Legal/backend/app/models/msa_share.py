from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MSAShare(Base):
    """Grants a user read or edit access to a specific MSA tracker."""

    __tablename__ = "msa_shares"
    __table_args__ = (UniqueConstraint("tracker_id", "user_id", name="uq_msa_share_tracker_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("msa_trackers.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shared_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    access_level: Mapped[str] = mapped_column(String(16), nullable=False, default="view")
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tracker: Mapped["MSATracker"] = relationship("MSATracker", back_populates="shares")  # noqa: F821
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # noqa: F821
    shared_by: Mapped["User"] = relationship("User", foreign_keys=[shared_by_id])  # noqa: F821
