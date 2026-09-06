"""Per-vendor token breakdown: vendor_id on llm_usage_logs

Revision ID: 012
Revises: 011
Create Date: 2026-07-26

Adds a nullable vendor_id FK so M2 due-diligence token usage can be attributed to
the vendor it screened. Additive and nullable — M1/M3 rows keep a null vendor.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_usage_logs",
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendors.id"), nullable=True),
    )
    op.create_index("ix_llm_usage_logs_vendor_id", "llm_usage_logs", ["vendor_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_logs_vendor_id", table_name="llm_usage_logs")
    op.drop_column("llm_usage_logs", "vendor_id")
