from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Task(Base):
    """Task Manager entries.

    Sources:
      - "email"     : extracted from Gmail intake (or simulated ingest)
      - "manual"    : user-created
      - "module"    : derived from another module (contract, msa, etc.) but
                      crystallised into a real task by the user
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_module: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email_sender: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email_subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    priority: Mapped[str] = mapped_column(String(4), nullable=False, default="P2")
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="todo")

    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
