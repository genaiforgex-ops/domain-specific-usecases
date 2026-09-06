"""design prompts — per-user override of the shared hero-image design base

Creates the design_prompts table: one row per user holding their replacement for the
built-in design-prompt base (brand photography scaffold). Empty by default — image
generation falls back to the built-in base.

Revision ID: b5d7f9a1c3e5
Revises: a4c6e8f0b2d3
Create Date: 2026-08-04 19:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5d7f9a1c3e5'
down_revision: Union[str, None] = 'a4c6e8f0b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'design_prompts',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('design_prompts')
