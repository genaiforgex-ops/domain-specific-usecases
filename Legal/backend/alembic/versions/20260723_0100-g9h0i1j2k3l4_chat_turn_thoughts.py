"""Add thoughts JSON column to chat turns (llm_turn_metrics)."""

from alembic import op
import sqlalchemy as sa

revision = "g9h0i1j2k3l4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_turn_metrics", sa.Column("thoughts", sa.JSON(), nullable=True))
    op.add_column("llm_turn_metrics", sa.Column("mode", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_turn_metrics", "mode")
    op.drop_column("llm_turn_metrics", "thoughts")
