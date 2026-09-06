"""Add agent_name column to llm_usage_logs for orchestrator governance."""

from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_usage_logs", sa.Column("agent_name", sa.String(length=64), nullable=True))
    op.create_index("ix_llm_usage_logs_agent_name", "llm_usage_logs", ["agent_name"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_logs_agent_name", table_name="llm_usage_logs")
    op.drop_column("llm_usage_logs", "agent_name")
