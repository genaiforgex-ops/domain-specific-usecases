"""username login handle; email no longer unique

Adds a unique `username` login handle and relaxes `email` to a non-unique
indexed column so several role accounts can share one inbox.

Revision ID: b3f7c1a9d2e4
Revises: d8e5cb615c88
Create Date: 2026-06-30 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7c1a9d2e4'
down_revision: Union[str, None] = 'd8e5cb615c88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New login handle. Added nullable, backfilled from the email local-part for
    # any existing rows, then made NOT NULL + unique.
    op.add_column('users', sa.Column('username', sa.String(length=64), nullable=True))
    op.execute("UPDATE users SET username = split_part(email, '@', 1) WHERE username IS NULL")
    op.alter_column('users', 'username', nullable=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Email is now a profile attribute — keep an index but drop the unique constraint.
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')
