"""Regulatory knowledge corpus: documents + clause-level chunks.

Postgres is the authoritative clause store. `regulatory_chunks.tsv` is a stored
generated column (to_tsvector is immutable, so Postgres can persist it) with a GIN
index, giving exact-term recall alongside the embedding vectors.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "i1j2k3l4m5n6"
down_revision = "h0i1j2k3l4m5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regulatory_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("issuer", sa.String(length=160), nullable=False),
        sa.Column("doc_type", sa.String(length=48), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="P3"),
        sa.Column(
            "update_cadence", sa.String(length=24), nullable=False, server_default="stable"
        ),
        sa.Column("canonical_url", sa.String(length=1024), nullable=True),
        sa.Column("direct_pdf_url", sa.String(length=1024), nullable=True),
        sa.Column("version_or_effective", sa.String(length=64), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("supersedes", sa.Text(), nullable=True),
        sa.Column("superseded_by", sa.String(length=64), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="missing"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("vertex_file_name", sa.String(length=512), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ingested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regulatory_documents_doc_id", "regulatory_documents", ["doc_id"], unique=True
    )
    op.create_index("ix_regulatory_documents_domain", "regulatory_documents", ["domain"])
    op.create_index("ix_regulatory_documents_doc_type", "regulatory_documents", ["doc_type"])
    op.create_index("ix_regulatory_documents_status", "regulatory_documents", ["status"])
    op.create_index(
        "ix_regulatory_documents_effective_date", "regulatory_documents", ["effective_date"]
    )
    op.create_index(
        "ix_regulatory_documents_superseded_by", "regulatory_documents", ["superseded_by"]
    )

    op.create_table(
        "regulatory_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_key", sa.String(length=160), nullable=False),
        sa.Column("section_label", sa.String(length=120), nullable=True),
        sa.Column("parent_heading", sa.String(length=512), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["regulatory_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regulatory_chunks_chunk_key", "regulatory_chunks", ["chunk_key"], unique=True
    )
    op.create_index("ix_regulatory_chunks_document_id", "regulatory_chunks", ["document_id"])
    op.create_index("ix_regulatory_chunks_doc_id", "regulatory_chunks", ["doc_id"])
    op.create_index("ix_regulatory_chunks_doc_ordinal", "regulatory_chunks", ["doc_id", "ordinal"])
    op.create_index(
        "ix_regulatory_chunks_tsv", "regulatory_chunks", ["tsv"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_regulatory_chunks_tsv", table_name="regulatory_chunks")
    op.drop_index("ix_regulatory_chunks_doc_ordinal", table_name="regulatory_chunks")
    op.drop_index("ix_regulatory_chunks_doc_id", table_name="regulatory_chunks")
    op.drop_index("ix_regulatory_chunks_document_id", table_name="regulatory_chunks")
    op.drop_index("ix_regulatory_chunks_chunk_key", table_name="regulatory_chunks")
    op.drop_table("regulatory_chunks")

    op.drop_index("ix_regulatory_documents_superseded_by", table_name="regulatory_documents")
    op.drop_index("ix_regulatory_documents_effective_date", table_name="regulatory_documents")
    op.drop_index("ix_regulatory_documents_status", table_name="regulatory_documents")
    op.drop_index("ix_regulatory_documents_doc_type", table_name="regulatory_documents")
    op.drop_index("ix_regulatory_documents_domain", table_name="regulatory_documents")
    op.drop_index("ix_regulatory_documents_doc_id", table_name="regulatory_documents")
    op.drop_table("regulatory_documents")
