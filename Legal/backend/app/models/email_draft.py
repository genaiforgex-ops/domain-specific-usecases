from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailDraft(Base):
    """AI-generated email reply awaiting user review and send."""

    __tablename__ = "email_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    original_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    original_body: Mapped[str] = mapped_column(Text, nullable=False)
    from_addr: Mapped[str] = mapped_column(String(256), nullable=False)
    to_addr: Mapped[str | None] = mapped_column(String(256), nullable=True)
    draft_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    draft_body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
