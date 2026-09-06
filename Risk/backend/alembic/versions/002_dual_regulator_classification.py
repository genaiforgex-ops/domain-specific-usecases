"""dual regulator classification columns

Revision ID: 002
Revises: 001
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("classification_jobs", sa.Column("rbi_label", sa.String(64), nullable=True))
    op.add_column("classification_jobs", sa.Column("rbi_confidence", sa.Float(), nullable=True))
    op.add_column("classification_jobs", sa.Column("rbi_evidence", JSONB(), nullable=True))
    op.add_column("classification_jobs", sa.Column("sebi_label", sa.String(64), nullable=True))
    op.add_column("classification_jobs", sa.Column("sebi_confidence", sa.Float(), nullable=True))
    op.add_column("classification_jobs", sa.Column("sebi_evidence", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("classification_jobs", "sebi_evidence")
    op.drop_column("classification_jobs", "sebi_confidence")
    op.drop_column("classification_jobs", "sebi_label")
    op.drop_column("classification_jobs", "rbi_evidence")
    op.drop_column("classification_jobs", "rbi_confidence")
    op.drop_column("classification_jobs", "rbi_label")
