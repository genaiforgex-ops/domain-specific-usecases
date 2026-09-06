"""Add feedback_comment column to chat turns (llm_turn_metrics)."""

from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_turn_metrics", sa.Column("feedback_comment", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_turn_metrics", "feedback_comment")
