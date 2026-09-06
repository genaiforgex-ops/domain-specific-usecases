"""add contract_revisions (UC-01 prompt-based document editor)

Revision ID: a1b2c3d4e5f6
Revises: 21cdf93c4e35
Create Date: 2026-06-15 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '21cdf93c4e35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contract_revisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('selection', sa.Text(), nullable=True),
        sa.Column('base_text', sa.Text(), nullable=False),
        sa.Column('edited_text', sa.Text(), nullable=False),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('diff_blocks', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='proposed'),
        sa.Column('model_version', sa.String(length=64), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_contract_revisions_contract_id'),
        'contract_revisions',
        ['contract_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_contract_revisions_contract_id'), table_name='contract_revisions')
    op.drop_table('contract_revisions')
