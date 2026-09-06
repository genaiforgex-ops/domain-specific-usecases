"""Add IAM sync tracking columns to users."""

from alembic import op
import sqlalchemy as sa

revision = "h0i1j2k3l4m5"
down_revision = "g9h0i1j2k3l4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("iam_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("iam_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("users", "iam_managed", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "iam_synced_at")
    op.drop_column("users", "iam_managed")
