from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MSAPromptRevision(Base):
    """Persisted prompt-edit proposal for MSA/NDA DOCX operation-based editing."""

    __tablename__ = "msa_prompt_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(
        ForeignKey("msa_trackers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_version_id: Mapped[int] = mapped_column(
        ForeignKey("msa_document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    selection: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    operations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    operation_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    structure_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    edit_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    diff_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resulting_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id"), nullable=True
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tracker: Mapped["MSATracker"] = relationship(foreign_keys=[tracker_id])  # noqa: F821
    base_version: Mapped["MSADocumentVersion"] = relationship(  # noqa: F821
        foreign_keys=[base_version_id]
    )
