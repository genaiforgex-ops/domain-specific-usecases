"""Real auth: password_hash + last_login on users; collapse roles to two

Revision ID: 009
Revises: 008
Create Date: 2026-07-26

Adds local-password login support. Both columns are nullable so existing rows are
untouched — a user with no password_hash just can't log in with email+password
until an admin sets one.

Also collapses the old six-role model down to two: the legacy "administrator"
role is renamed to "admin" (kept alongside "risk_manager"). Leftover
analyst/compliance/procurement/auditor role rows are left in place but are no
longer recognised by the permission map, so those demo users have no access and
can be deleted from User Management.
"""
import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE user_roles SET role = 'admin' WHERE role = 'administrator'")


def downgrade() -> None:
    op.execute("UPDATE user_roles SET role = 'administrator' WHERE role = 'admin'")
    op.drop_column("users", "last_login")
    op.drop_column("users", "password_hash")
