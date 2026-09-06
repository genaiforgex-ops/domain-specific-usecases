"""msa intelligence phase3

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("msa_trackers", sa.Column("review_guidelines", sa.Text(), nullable=True))
    op.add_column(
        "negotiation_change_tasks",
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "negotiation_change_tasks",
        sa.Column("promoted_task_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_negotiation_task_promoted",
        "negotiation_change_tasks",
        "tasks",
        ["promoted_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "negotiation_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tracker_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tracker_id"], ["msa_trackers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["msa_document_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_negotiation_memory_tracker_id", "negotiation_memory", ["tracker_id"])
    op.add_column("legal_bot_queries", sa.Column("context_type", sa.String(length=32), nullable=True))
    op.add_column("legal_bot_queries", sa.Column("context_tracker_id", sa.Integer(), nullable=True))
    op.add_column("legal_bot_queries", sa.Column("context_version_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("legal_bot_queries", "context_version_id")
    op.drop_column("legal_bot_queries", "context_tracker_id")
    op.drop_column("legal_bot_queries", "context_type")
    op.drop_index("ix_negotiation_memory_tracker_id", table_name="negotiation_memory")
    op.drop_table("negotiation_memory")
    op.drop_constraint("fk_negotiation_task_promoted", "negotiation_change_tasks", type_="foreignkey")
    op.drop_column("negotiation_change_tasks", "promoted_task_id")
    op.drop_column("negotiation_change_tasks", "due_date")
    op.drop_column("msa_trackers", "review_guidelines")
