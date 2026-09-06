"""Add sources + feedback columns to chat turns (llm_turn_metrics)."""

from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_turn_metrics", sa.Column("sources", sa.JSON(), nullable=True))
    op.add_column("llm_turn_metrics", sa.Column("feedback", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_turn_metrics", "feedback")
    op.drop_column("llm_turn_metrics", "sources")
