"""five roles + reordered approval

Collapse to 5 roles (drop Strategist) and reorder the approval pipeline:
  draft → brief_review(ML) → copywriting(CW) → design(DS) →
  creative_review(ML) → final_signoff(PL) → completed

- Replace the parallel 3-lane gate (gate1_strategy/marketing/product) with three
  sequential single-approver checkpoints (brief_review / creative_review /
  final_signoff), each with state/_by_id/_at columns.
- Drop the Strategist strategy block (strategist_id, channel_mix, target_audience,
  creative_prompt, strategy_authorized_at). budget_inr is kept for display.
- Migrate live rows: any brief sitting in the old 'approval' stage bounces back to
  'copywriting'; existing ST accounts are retired to inactive (roles are validated
  against the new set on write).

Revision ID: b8d2f3a4c5e6
Revises: a7c4e9f10b23
Create Date: 2026-07-16 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d2f3a4c5e6'
down_revision: Union[str, None] = 'a7c4e9f10b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_STATE_COLS = ("brief_review_state", "creative_review_state", "final_signoff_state")
_NEW_ID_COLS = ("brief_review_by_id", "creative_review_by_id", "final_signoff_by_id")
_NEW_AT_COLS = ("brief_review_at", "creative_review_at", "final_signoff_at")

_OLD_GATE_COLS = (
    "gate1_strategy", "gate1_marketing", "gate1_product",
    "gate1_strategy_by_id", "gate1_marketing_by_id", "gate1_product_by_id",
    "gate1_strategy_at", "gate1_marketing_at", "gate1_product_at",
)
_OLD_STRATEGY_COLS = (
    "channel_mix", "target_audience", "creative_prompt", "strategy_authorized_at",
)


def upgrade() -> None:
    # New approval checkpoints.
    for col in _NEW_STATE_COLS:
        op.add_column(
            "briefs",
            sa.Column(col, sa.String(length=24), nullable=False, server_default="pending"),
        )
    for col in _NEW_ID_COLS:
        op.add_column("briefs", sa.Column(col, sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_briefs_{col}_users", "briefs", "users", [col], ["id"], ondelete="SET NULL"
        )
    for col in _NEW_AT_COLS:
        op.add_column("briefs", sa.Column(col, sa.DateTime(timezone=True), nullable=True))

    # Data migration for live rows before the old shape disappears.
    op.execute("UPDATE briefs SET stage = 'copywriting' WHERE stage = 'approval'")
    # Retire Strategist accounts — role no longer exists.
    op.execute("UPDATE users SET is_active = false WHERE role = 'ST'")

    # Drop the old parallel gate + the strategy block. budget_inr stays.
    for col in (*_OLD_GATE_COLS, "strategist_id", *_OLD_STRATEGY_COLS):
        op.drop_column("briefs", col)

    # Server defaults were only needed to backfill existing rows.
    for col in _NEW_STATE_COLS:
        op.alter_column("briefs", col, server_default=None)


def downgrade() -> None:
    op.add_column("briefs", sa.Column("strategist_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "briefs_strategist_id_fkey", "briefs", "users", ["strategist_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("briefs", sa.Column("channel_mix", sa.Text(), nullable=True))
    op.add_column("briefs", sa.Column("target_audience", sa.Text(), nullable=True))
    op.add_column("briefs", sa.Column("creative_prompt", sa.Text(), nullable=True))
    op.add_column("briefs", sa.Column("strategy_authorized_at", sa.DateTime(timezone=True), nullable=True))
    for lane in ("strategy", "marketing", "product"):
        op.add_column(
            "briefs",
            sa.Column(f"gate1_{lane}", sa.String(length=24), nullable=False, server_default="pending"),
        )
        op.add_column("briefs", sa.Column(f"gate1_{lane}_by_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_briefs_gate1_{lane}_by_id_users", "briefs", "users",
            [f"gate1_{lane}_by_id"], ["id"], ondelete="SET NULL",
        )
        op.add_column("briefs", sa.Column(f"gate1_{lane}_at", sa.DateTime(timezone=True), nullable=True))
        op.alter_column("briefs", f"gate1_{lane}", server_default=None)

    op.execute("UPDATE briefs SET stage = 'approval' WHERE stage = 'brief_review'")
    op.execute(
        "UPDATE briefs SET stage = 'design' "
        "WHERE stage IN ('creative_review', 'final_signoff', 'completed')"
    )

    for col in (*_NEW_AT_COLS, *_NEW_ID_COLS, *_NEW_STATE_COLS):
        op.drop_column("briefs", col)
