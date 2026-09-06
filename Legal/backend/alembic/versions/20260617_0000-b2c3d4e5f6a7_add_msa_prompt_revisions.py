"""add msa_prompt_revisions and docx structure columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-17 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("msa_document_versions", sa.Column("structure_snapshot", sa.JSON(), nullable=True))
    op.add_column("msa_document_versions", sa.Column("structure_hash", sa.String(length=64), nullable=True))

    op.create_table(
        "msa_prompt_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tracker_id", sa.Integer(), nullable=False),
        sa.Column("base_version_id", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("selection", sa.Text(), nullable=True),
        sa.Column("base_text", sa.Text(), nullable=False),
        sa.Column("edited_text", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("operations", sa.JSON(), nullable=True),
        sa.Column("operation_results", sa.JSON(), nullable=True),
        sa.Column("structure_hash", sa.String(length=64), nullable=True),
        sa.Column("edit_mode", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("diff_blocks", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("resulting_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tracker_id"], ["msa_trackers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_version_id"], ["msa_document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resulting_version_id"], ["msa_document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_msa_prompt_revisions_tracker_id"),
        "msa_prompt_revisions",
        ["tracker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_msa_prompt_revisions_base_version_id"),
        "msa_prompt_revisions",
        ["base_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_msa_prompt_revisions_base_version_id"), table_name="msa_prompt_revisions")
    op.drop_index(op.f("ix_msa_prompt_revisions_tracker_id"), table_name="msa_prompt_revisions")
    op.drop_table("msa_prompt_revisions")
    op.drop_column("msa_document_versions", "structure_hash")
    op.drop_column("msa_document_versions", "structure_snapshot")
