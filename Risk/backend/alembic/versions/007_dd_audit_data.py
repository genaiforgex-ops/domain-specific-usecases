"""vendor DD rich audit_data + error columns

Revision ID: 007
Revises: 006
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dd_reports", sa.Column("audit_data", JSONB(), nullable=True))
    op.add_column("dd_reports", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dd_reports", "error")
    op.drop_column("dd_reports", "audit_data")
