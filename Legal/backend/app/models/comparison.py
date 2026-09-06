from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentComparison(Base):
    """UC-02 Document Comparison: two versions of a doc and their diff."""

    __tablename__ = "document_comparisons"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    v1_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    v2_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    v1_text: Mapped[str] = mapped_column(Text, nullable=False)
    v2_text: Mapped[str] = mapped_column(Text, nullable=False)
    diff_blocks: Mapped[list] = mapped_column(JSON, nullable=False)
    risk_commentary: Mapped[list] = mapped_column(JSON, nullable=False)
    summary_report: Mapped[str] = mapped_column(Text, nullable=False)
    llm_narrative: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tracker_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_trackers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    from_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id", ondelete="SET NULL"), nullable=True
    )
    to_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id", ondelete="SET NULL"), nullable=True
    )
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
