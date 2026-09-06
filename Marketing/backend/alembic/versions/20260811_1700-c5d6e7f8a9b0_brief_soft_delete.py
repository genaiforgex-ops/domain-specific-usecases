"""soft-delete for briefs

Discarding a draft/returned brief now stamps ``deleted_at`` instead of destroying
the row, so the "deleted" audit entry (and the brief's whole history) survives and
stays visible in the audit log. Every user-facing brief list/detail filters these
out; only the audit trail still surfaces them.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-11 17:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'briefs',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f('ix_briefs_deleted_at'), 'briefs', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_briefs_deleted_at'), table_name='briefs')
    op.drop_column('briefs', 'deleted_at')
