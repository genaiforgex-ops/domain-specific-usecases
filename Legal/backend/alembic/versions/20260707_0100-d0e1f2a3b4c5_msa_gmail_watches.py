"""Add MSA Gmail watched threads and tracker auto-ingest flag."""

from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gmail_settings",
        sa.Column("msa_watched_threads", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "msa_trackers",
        sa.Column("gmail_auto_ingest", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("msa_trackers", "gmail_auto_ingest")
    op.drop_column("gmail_settings", "msa_watched_threads")
