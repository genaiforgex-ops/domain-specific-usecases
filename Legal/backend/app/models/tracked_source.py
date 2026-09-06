"""Regulator source websites the legal team tracks (UC-06).

Each row is a website/feed the Regulatory Intelligence scraper polls (RBI, SEBI,
IRDAI, ASCI, …). Distinct from `RegulatorySource` (a static RAG corpus doc) —
this models a *subscribed site to fetch*, with polling state.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrackedSource(Base):
    __tablename__ = "tracked_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    regulator: Mapped[str] = mapped_column(String(64), nullable=False, default="Other")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Other")
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="web")  # web | rss
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    added_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
