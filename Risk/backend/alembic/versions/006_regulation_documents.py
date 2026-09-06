"""Add regulation_documents table (self-service Library uploads)

Revision ID: 006
Revises: 005
Create Date: 2026-07-02

Until now, ingesting a new regulator PDF required a developer to drop the
file into resources/regulations/ and run load_clauses.py by hand — and
clause "version" was a single global string (get_active_clause_version()
in classification_service.py) shared across every regulator/instrument, so
there was no way to stop using one document's clauses without touching
everyone else's.

This migration adds regulation_documents — one row per uploaded PDF, each
independently "pending_review" / "active" / "archived" — and links
regulator_clauses to it via a nullable document_id (nullable so the 3
legacy startup-seeded clauses aren't forced to backfill immediately; see
app/scripts/regulation_ingest/backfill_documents.py, which populates it for
them anyway so there's one lookup path going forward).

classification_jobs gets clause_document_ids (JSONB), a snapshot of which
documents were active when a job was created. run_classification() prefers
this when present and falls back to the legacy clause_library_version
lookup when null — every job created before this migration keeps resolving
exactly as it did before, untouched.

PDF bytes are stored in Postgres (pdf_bytes, bytea) rather than object
storage: it keeps the source PDF next to its clauses for citation-
highlighting with no extra bucket wiring. Fine at the scale of a few dozen
regulation PDFs.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regulation_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("regulator", sa.String(32), nullable=False),
        sa.Column("instrument", sa.String(64), nullable=False),
        sa.Column("source_doc", sa.String(256), nullable=False),
        sa.Column("ref_prefix", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_regulation_documents_status", "regulation_documents", ["status"])

    op.add_column(
        "regulator_clauses",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("regulation_documents.id"), nullable=True),
    )
    op.create_index("ix_regulator_clauses_document_id", "regulator_clauses", ["document_id"])

    op.add_column("classification_jobs", sa.Column("clause_document_ids", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("classification_jobs", "clause_document_ids")
    op.drop_index("ix_regulator_clauses_document_id", table_name="regulator_clauses")
    op.drop_column("regulator_clauses", "document_id")
    op.drop_index("ix_regulation_documents_status", table_name="regulation_documents")
    op.drop_table("regulation_documents")
