"""The regulatory knowledge corpus — statutes, master directions and circulars
the bot cites, stored clause by clause.

Postgres is authoritative here: it owns the clause text, the provision labels the
citations are built from, the effective/supersession dates that keep repealed law
out of answers, and the embedding vectors. The optional Vertex corpus only adds a
second doc-level recall channel (`vertex_file_name`), so losing it degrades recall
without affecting correctness.

Distinct from `TrackedSource` (a website the news scraper polls) and
`RegulatorySource` (a legacy static reference row).
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Ingestion status of a manifest row.
STATUS_MISSING = "missing"
STATUS_INGESTED = "ingested"
STATUS_STALE = "stale"
STATUS_FAILED = "failed"


class RegulatoryDocument(Base):
    """One ingested manifest document (a statute, master direction, circular…)."""

    __tablename__ = "regulatory_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable manifest key, e.g. "LEND-DLD-2025". Also the citation anchor.
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str] = mapped_column(String(160), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P3")
    update_cadence: Mapped[str] = mapped_column(String(24), nullable=False, default="stable")
    canonical_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    direct_pdf_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Version as written in the manifest ("2025-05-08" or "check-latest"), plus the
    # parsed date when there is one. `superseded_by` holds the doc_id that replaced
    # this one and is what the as-of filter keys off.
    version_or_effective: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    supersedes: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Original PDF/HTML in GCS (or the local backend) for the Evidence panel.
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_MISSING, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Vertex RagFile resource name when the optional recall channel is enabled.
    vertex_file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)

    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    chunks: Mapped[list["RegulatoryChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class RegulatoryChunk(Base):
    """One clause-level provision of a regulatory document.

    Chunks follow the legal hierarchy rather than a character budget, so
    `section_label` ("Para 5.3", "Section 43A") can be cited verbatim.
    """

    __tablename__ = "regulatory_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized so retrieval can filter/join without touching the parent row.
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Human-readable stable id, e.g. "LEND-DLD-2025:para-5-3".
    chunk_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)

    section_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_heading: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # float32 little-endian, L2-normalized, `regulatory_embed_dims` wide.
    # Plain bytes because pgvector is not available on this instance; similarity is
    # a cached numpy matmul in regulatory_rag_service.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # NOTE: the table also has a `tsv` column — a Postgres stored generated column
    # (`to_tsvector('english', text)`) with a GIN index, created by the Alembic
    # migration. It is deliberately NOT mapped here: it is written by Postgres, only
    # ever read through raw SQL in `regulatory_rag_service`, and mapping a TSVECTOR
    # would make `Base.metadata.create_all` unusable on SQLite (which unit tests use).

    document: Mapped[RegulatoryDocument] = relationship(back_populates="chunks")

    __table_args__ = (Index("ix_regulatory_chunks_doc_ordinal", "doc_id", "ordinal"),)
