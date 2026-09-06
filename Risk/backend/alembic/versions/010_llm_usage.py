"""LLM usage log for token/metrics accounting

Revision ID: 010
Revises: 009
Create Date: 2026-07-26

One row per AI model invocation (M1 classify, M2 audit). Additive — no existing
table is touched, so AI flows keep working whether or not a row gets written.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("module", sa.String(16), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_llm_usage_logs_actor_id", "llm_usage_logs", ["actor_id"])
    op.create_index("ix_llm_usage_logs_module", "llm_usage_logs", ["module"])
    op.create_index("ix_llm_usage_logs_created_at", "llm_usage_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_logs_created_at", table_name="llm_usage_logs")
    op.drop_index("ix_llm_usage_logs_module", table_name="llm_usage_logs")
    op.drop_index("ix_llm_usage_logs_actor_id", table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")
