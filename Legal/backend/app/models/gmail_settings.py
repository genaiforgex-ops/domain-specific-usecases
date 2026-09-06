from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GmailSettings(Base):
    """Per-user Gmail polling and ingestion preferences."""

    __tablename__ = "gmail_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    poll_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    poll_labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    auto_task_ingest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    poll_lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    watched_threads: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    watched_senders: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    msa_watched_threads: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    processed_message_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    default_context_module: Mapped[str] = mapped_column(String(32), nullable=False, default="tasks")
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
