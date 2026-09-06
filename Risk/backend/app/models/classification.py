import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RegulationDocument(Base):
    """One uploaded regulator PDF ('Library' item). Its clauses (RegulatorClause
    rows linked via document_id) only feed classification while status='active'
    — archiving a document removes just its clauses from the pool without
    touching any other document's version or clauses."""

    __tablename__ = "regulation_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    regulator: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument: Mapped[str] = mapped_column(String(64), nullable=False)
    source_doc: Mapped[str] = mapped_column(String(256), nullable=False)
    ref_prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    # Stored in Postgres rather than object storage: keeps the source PDF right
    # next to the clauses for citation-highlighting, with no extra bucket wiring.
    # Fine at this scale (a few dozen regulation PDFs, not
    # thousands).
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # "processing" (just uploaded, PDF not chunked yet) -> "pending_review"
    # (clauses extracted, awaiting activation) -> "active" | "failed" |
    # "archived". See library_service.py for the transitions.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing", index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegulatorClause(Base):
    __tablename__ = "regulator_clauses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    regulator: Mapped[str] = mapped_column(String(32), nullable=False)
    clause_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Which specific regulation within `regulator` this clause came from, e.g.
    # "NBFC" / "PAYMENTS_BANK" / "IA" — lets RBI's multiple outsourcing
    # directions coexist without collapsing into one bucket.
    instrument: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_doc: Mapped[str | None] = mapped_column(String(256), nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    para_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Nullable so the 3 legacy startup-seeded clauses don't strictly require
    # backfilling, though the backfill script populates this for them too so
    # there's a single lookup path (see backfill_documents.py).
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulation_documents.id"), nullable=True, index=True
    )


class ClassificationJob(Base):
    __tablename__ = "classification_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    ai_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rbi_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rbi_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rbi_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sebi_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sebi_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sebi_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    secondary_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    clause_library_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Snapshot of active RegulationDocument IDs at job-creation time. When
    # set, run_classification() loads clauses by these IDs instead of by
    # clause_library_version — lets documents be archived independently
    # without a single global version string gating everything. Null on
    # every job created before this column existed; those keep resolving via
    # clause_library_version so old results stay reproducible.
    clause_document_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # The classification agents the user chose for this job. Null/empty means the
    # built-in default prompt runs (unchanged legacy behavior); a non-empty list
    # runs each agent and records a ClassificationAgentRun per agent.
    agent_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    requires_secondary_review: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="classification_jobs")
    # The file the analyst attached when submitting the assessment (if any).
    # selectin-loaded so list/detail endpoints can surface its filename without
    # a lazy load (which would fail under async) or an N+1 per row.
    document: Mapped["Document | None"] = relationship("Document", lazy="selectin")
    # Per-agent results for jobs run with one or more selected agents. selectin so
    # the detail endpoint can render the side-by-side comparison without a lazy
    # load; cascade delete so a job's runs go with it.
    agent_runs: Mapped[list["ClassificationAgentRun"]] = relationship(
        "ClassificationAgentRun",
        back_populates="job",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def document_filename(self) -> str | None:
        # Never trigger a lazy load here: after db.refresh() the relationship is
        # expired, and touching it under async would raise MissingGreenlet. When
        # unloaded, report None — the list/detail queries selectin-load it, so
        # the filename still shows there.
        from sqlalchemy import inspect as sa_inspect

        if "document" in sa_inspect(self).unloaded:
            return None
        return self.document.filename if self.document else None
