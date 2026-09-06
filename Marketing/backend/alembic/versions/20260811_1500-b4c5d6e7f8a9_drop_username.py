"""drop the legacy username login handle

There is no username concept anymore: sign-in identity is the email (Jio SSO)
and roles come from Central IAM. The column and its unique index were already
unused (nullable since the SSO migration); this removes them entirely.

Revision ID: b4c5d6e7f8a9
Revises: a2b3c4d5e6f7
Create Date: 2026-08-11 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')


def downgrade() -> None:
    # Recreate the column as nullable (the old handles are not recoverable).
    op.add_column('users', sa.Column('username', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
