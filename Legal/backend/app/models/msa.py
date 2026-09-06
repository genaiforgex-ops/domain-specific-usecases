from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MSATracker(Base):
    """UC-05 MSA / NDA Automation tracker.

    One row per contract negotiation thread. Status moves through:
    draft → under_review → redlined → sent_to_vendor → negotiation → executed.
    """

    __tablename__ = "msa_trackers"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String(256), nullable=False)
    vendor_email: Mapped[str] = mapped_column(String(256), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MSA")
    deal_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_version: Mapped[int] = mapped_column(nullable=False, default=1)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    redlined_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_suggestions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_templates.id"), nullable=True
    )
    canonical_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id", use_alter=True, name="fk_msa_canonical_version"),
        nullable=True,
    )
    executed_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id", use_alter=True, name="fk_msa_executed_version"),
        nullable=True,
    )
    gmail_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gmail_auto_ingest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_guidelines: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    emails: Mapped[list["MSAEmail"]] = relationship(
        back_populates="tracker", cascade="all, delete-orphan", order_by="MSAEmail.sent_at"
    )
    versions: Mapped[list["MSADocumentVersion"]] = relationship(  # noqa: F821
        "MSADocumentVersion",
        back_populates="tracker",
        cascade="all, delete-orphan",
        order_by="MSADocumentVersion.version_number",
        foreign_keys="[MSADocumentVersion.tracker_id]",
    )
    canonical_version: Mapped["MSADocumentVersion | None"] = relationship(  # noqa: F821
        "MSADocumentVersion",
        foreign_keys=[canonical_version_id],
        uselist=False,
    )
    executed_version: Mapped["MSADocumentVersion | None"] = relationship(  # noqa: F821
        "MSADocumentVersion",
        foreign_keys=[executed_version_id],
        uselist=False,
    )
    shares: Mapped[list["MSAShare"]] = relationship(  # noqa: F821
        "MSAShare",
        back_populates="tracker",
        cascade="all, delete-orphan",
    )


class MSAEmail(Base):
    __tablename__ = "msa_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(
        ForeignKey("msa_trackers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("msa_document_versions.id", ondelete="SET NULL"), nullable=True
    )
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # "in" or "out"
    from_addr: Mapped[str] = mapped_column(String(256), nullable=False)
    to_addr: Mapped[str] = mapped_column(String(256), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attachment_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    tracker: Mapped[MSATracker] = relationship(back_populates="emails")
