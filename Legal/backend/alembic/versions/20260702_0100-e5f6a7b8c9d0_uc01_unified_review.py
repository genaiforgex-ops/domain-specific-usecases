"""uc01 unified review

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("playbook_clauses", sa.Column("fallback_text", sa.Text(), nullable=True))
    op.add_column(
        "playbook_clauses",
        sa.Column("regulatory_tags", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "playbook_clauses",
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "playbook_clauses",
        sa.Column("insert_anchor_hint", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "clause_bank_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playbook_clause_id", sa.Integer(), nullable=True),
        sa.Column("contract_type", sa.String(length=32), nullable=False),
        sa.Column("clause_type", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False, server_default="preferred"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("regulatory_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["playbook_clause_id"],
            ["playbook_clauses.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_clause_bank_contract_type",
        "clause_bank_entries",
        ["contract_type"],
    )

    op.add_column("contracts", sa.Column("review_guidelines", sa.Text(), nullable=True))
    op.add_column("contracts", sa.Column("ai_suggestions", sa.JSON(), nullable=True))
    op.add_column("contracts", sa.Column("change_history", sa.JSON(), nullable=True))

    op.add_column("msa_trackers", sa.Column("change_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("msa_trackers", "change_history")
    op.drop_column("contracts", "change_history")
    op.drop_column("contracts", "ai_suggestions")
    op.drop_column("contracts", "review_guidelines")
    op.drop_index("ix_clause_bank_contract_type", table_name="clause_bank_entries")
    op.drop_table("clause_bank_entries")
    op.drop_column("playbook_clauses", "insert_anchor_hint")
    op.drop_column("playbook_clauses", "is_required")
    op.drop_column("playbook_clauses", "regulatory_tags")
    op.drop_column("playbook_clauses", "fallback_text")
