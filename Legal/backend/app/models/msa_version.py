from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MSADocumentVersion(Base):
    """Immutable revision in an MSA/NDA negotiation chain."""

    __tablename__ = "msa_document_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(
        ForeignKey("msa_trackers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id"), nullable=True
    )
    comparison_id: Mapped[int | None] = mapped_column(
        # use_alter: breaks the circular FK between msa_document_versions and
        # document_comparisons so Alembic can order CREATE TABLE statements.
        ForeignKey(
            "document_comparisons.id",
            name="fk_msa_version_comparison",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    structure_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    structure_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tracker: Mapped["MSATracker"] = relationship(  # noqa: F821
        back_populates="versions",
        foreign_keys=[tracker_id],
    )
