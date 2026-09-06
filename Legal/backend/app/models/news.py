from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RegulatoryUpdate(Base):
    """UC-06 Legal News & Regulatory Monitoring.

    One row per ingested regulatory update (RBI / SEBI / IRDAI / MCA / DPDP /
    PMLA / court judgment) — AI-summarised, tagged, scored.
    """

    __tablename__ = "regulatory_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracked_sources.id", ondelete="SET NULL"), index=True, nullable=True
    )
    category: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="for_information")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    triaged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    impact_note: Mapped[str | None] = mapped_column(Text, nullable=True)
