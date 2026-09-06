"""agent prompts — per-user custom agent instructions (Agent Studio)

Revision ID: c9e3a5b7d1f8
Revises: b8d2f3a4c5e6
Create Date: 2026-07-21 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e3a5b7d1f8'
down_revision: Union[str, None] = 'b8d2f3a4c5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_prompts',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('agent_kind', sa.String(length=16), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'agent_kind'),
    )


def downgrade() -> None:
    op.drop_table('agent_prompts')
