"""Add Gmail watch lists and poll lookback days."""

from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gmail_settings",
        sa.Column("poll_lookback_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.add_column(
        "gmail_settings",
        sa.Column("watched_threads", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "gmail_settings",
        sa.Column("watched_senders", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("gmail_settings", "watched_senders")
    op.drop_column("gmail_settings", "watched_threads")
    op.drop_column("gmail_settings", "poll_lookback_days")
