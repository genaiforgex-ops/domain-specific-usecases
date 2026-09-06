"""Per-agent token breakdown: agent_name on llm_usage_logs

Revision ID: 011
Revises: 010
Create Date: 2026-07-26

Adds a nullable agent_name column so M1 token usage can be attributed to the
classification agent that produced it ("Default" for the built-in run). Additive
and nullable — existing rows keep working with a null agent.
"""
import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_usage_logs", sa.Column("agent_name", sa.String(128), nullable=True))
    op.create_index("ix_llm_usage_logs_agent_name", "llm_usage_logs", ["agent_name"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_logs_agent_name", table_name="llm_usage_logs")
    op.drop_column("llm_usage_logs", "agent_name")
