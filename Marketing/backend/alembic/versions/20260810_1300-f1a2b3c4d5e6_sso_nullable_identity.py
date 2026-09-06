"""sso: username + password optional (email is the identity)

Jio SSO makes email the login identity and Central IAM the source of roles.
SSO-only accounts have no local password and no username, so both columns become
nullable. Existing rows are left untouched (the unique index on username still
allows multiple NULLs in Postgres).

Revision ID: f1a2b3c4d5e6
Revises: e5a7c9b1d3f6
Create Date: 2026-08-10 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5a7c9b1d3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'username', existing_type=sa.String(length=64), nullable=True)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # Backfill so the NOT NULL restore can't fail on SSO-provisioned rows.
    op.execute("UPDATE users SET username = split_part(email, '@', 1) WHERE username IS NULL")
    op.execute("UPDATE users SET hashed_password = '' WHERE hashed_password IS NULL")
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=False)
    op.alter_column('users', 'username', existing_type=sa.String(length=64), nullable=False)
