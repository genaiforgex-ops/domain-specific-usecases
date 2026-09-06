from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NegotiationChangeTask(Base):
    """Legal work item derived from a version diff."""

    __tablename__ = "negotiation_change_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(
        ForeignKey("msa_trackers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id", ondelete="SET NULL"), nullable=True
    )
    comparison_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_comparisons.id", ondelete="SET NULL"), nullable=True
    )
    diff_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clause_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
