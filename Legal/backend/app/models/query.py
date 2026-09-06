from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LegalBotQuery(Base):
    """UC-03 Basic Legal Queries (LegalBot).

    Stored per user. Tier-1 queries are auto-answered with citations;
    Tier-2 queries are escalated to the Legal team dashboard.
    """

    __tablename__ = "legal_bot_queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ai_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tier: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="answered")
    legal_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_tracker_id: Mapped[int | None] = mapped_column(nullable=True)
    context_version_id: Mapped[int | None] = mapped_column(nullable=True)
    context_gmail_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
