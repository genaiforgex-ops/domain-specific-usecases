"""Chatbot orchestrator: session index + per-turn metrics.

Adds the app-owned chat tables. The ADK DatabaseSessionService creates and
manages its OWN session/event/state tables at runtime (it uses a separate async
engine and introspects/creates on first use); those are intentionally NOT
declared here. This migration owns only the LegalOS-side records:
  - chat_sessions:   sidebar index (title, owner, activity)
  - llm_turn_metrics: durable per-turn log (query, response, tokens, latency)
"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="New Chat Session"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    op.create_table(
        "llm_turn_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("bot_response", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_llm_turn_metrics_session_id", "llm_turn_metrics", ["session_id"])
    op.create_index("ix_llm_turn_metrics_user_id", "llm_turn_metrics", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_turn_metrics_user_id", table_name="llm_turn_metrics")
    op.drop_index("ix_llm_turn_metrics_session_id", table_name="llm_turn_metrics")
    op.drop_table("llm_turn_metrics")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
