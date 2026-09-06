"""sso: collapse duplicate-email accounts to one active row

The pre-SSO model created a separate account per role, so one person could hold
several rows sharing an email (e.g. abhijeet.ad / abhijeet.cp / abhijeet.pl).
SSO makes email the login identity, and the lookup refuses to guess when an
email maps to multiple active rows — so those legacy duplicates block login.

This keeps ONE active row per email and deactivates the rest (is_active=False).
Rows are never deleted, so foreign keys from briefs / assignments / creatives
stay intact. The keeper is chosen deterministically: an account with a local
password wins (password login keeps working), then an AD account, then the
earliest-created / lowest id. Idempotent: emails already down to one active row
are untouched, so re-running is a no-op.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-10 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY lower(email)
                       ORDER BY (hashed_password IS NOT NULL) DESC,
                                (role = 'AD') DESC,
                                created_at ASC NULLS LAST,
                                id ASC
                   ) AS rn
            FROM users
            WHERE is_active = TRUE
        )
        UPDATE users u
        SET is_active = FALSE
        FROM ranked r
        WHERE u.id = r.id AND r.rn > 1
        """
    )


def downgrade() -> None:
    # Irreversible data cleanup: the original per-row is_active state is not
    # recorded, so we can't reactivate the collapsed accounts. No-op.
    pass
