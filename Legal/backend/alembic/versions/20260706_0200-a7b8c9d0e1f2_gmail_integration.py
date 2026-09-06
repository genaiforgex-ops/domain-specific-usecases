"""gmail integration tables

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("poll_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("poll_labels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("auto_task_ingest", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("processed_message_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("default_context_module", sa.String(length=32), nullable=False, server_default="tasks"),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "email_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=128), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=128), nullable=False),
        sa.Column("original_subject", sa.String(length=512), nullable=False),
        sa.Column("original_body", sa.Text(), nullable=False),
        sa.Column("from_addr", sa.String(length=256), nullable=False),
        sa.Column("to_addr", sa.String(length=256), nullable=True),
        sa.Column("draft_subject", sa.String(length=512), nullable=False),
        sa.Column("draft_body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_drafts_gmail_thread_id", "email_drafts", ["gmail_thread_id"])
    op.create_index("ix_email_drafts_gmail_message_id", "email_drafts", ["gmail_message_id"])
    op.add_column("tasks", sa.Column("gmail_message_id", sa.String(length=128), nullable=True))
    op.add_column("tasks", sa.Column("gmail_thread_id", sa.String(length=128), nullable=True))
    op.create_index("ix_tasks_gmail_message_id", "tasks", ["gmail_message_id"])
    op.create_index("ix_tasks_gmail_thread_id", "tasks", ["gmail_thread_id"])
    op.add_column(
        "legal_bot_queries",
        sa.Column("context_gmail_thread_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legal_bot_queries", "context_gmail_thread_id")
    op.drop_index("ix_tasks_gmail_thread_id", table_name="tasks")
    op.drop_index("ix_tasks_gmail_message_id", table_name="tasks")
    op.drop_column("tasks", "gmail_thread_id")
    op.drop_column("tasks", "gmail_message_id")
    op.drop_index("ix_email_drafts_gmail_message_id", table_name="email_drafts")
    op.drop_index("ix_email_drafts_gmail_thread_id", table_name="email_drafts")
    op.drop_table("email_drafts")
    op.drop_table("gmail_settings")
