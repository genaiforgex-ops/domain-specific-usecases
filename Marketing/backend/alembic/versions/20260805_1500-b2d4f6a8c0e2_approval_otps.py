"""approval otps — server-side guess limit for email-approval codes

Creates the approval_otps table: one row per issued one-time code, keyed by the
signed token's `jti`. Holds the wrong-guess count and a single-use flag, so the
6-digit code has a real budget. A counter carried inside the token could not do
this — replaying the first token resets it to zero for free.

Revision ID: b2d4f6a8c0e2
Revises: a1b3c5d7e9f1
Create Date: 2026-08-05 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c0e2'
down_revision: Union[str, None] = 'a1b3c5d7e9f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'approval_otps',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brief_id', sa.UUID(), nullable=False),
        sa.Column('approver_id', sa.UUID(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consumed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brief_id'], ['briefs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_approval_otps_brief_id', 'approval_otps', ['brief_id'])
    op.create_index('ix_approval_otps_approver_id', 'approval_otps', ['approver_id'])


def downgrade() -> None:
    op.drop_index('ix_approval_otps_approver_id', table_name='approval_otps')
    op.drop_index('ix_approval_otps_brief_id', table_name='approval_otps')
    op.drop_table('approval_otps')
