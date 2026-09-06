"""role defaults — default assignee per role

Revision ID: f5a1c2d3e4b6
Revises: c4a9e7f21b8d
Create Date: 2026-07-09 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5a1c2d3e4b6'
down_revision: Union[str, None] = 'c4a9e7f21b8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'role_defaults',
        sa.Column('role', sa.String(length=8), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role'),
    )


def downgrade() -> None:
    op.drop_table('role_defaults')
