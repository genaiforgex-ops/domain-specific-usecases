"""banner categories — PL picks a template *category* at brief creation

Two-level model:
  * banner_templates gain a `category` slug (the template family: "performance"
    statics vs "messaging" WhatsApp/RCS/RPN). Many templates can share a category.
  * briefs gain `banner_category` — the family the Product Lead picks up front. It
    locks which templates the Designer may work from; the Designer still picks the
    specific template within it. Nullable so pre-existing briefs fall back to all.

Backfills the two seeded templates into their categories.

Revision ID: a1b3c5d7e9f1
Revises: f9b2d4c6e8a0
Create Date: 2026-08-05 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b3c5d7e9f1'
down_revision: Union[str, None] = 'f9b2d4c6e8a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MESSAGING_NAME = "Messaging — WhatsApp / RCS / RPN"


def upgrade() -> None:
    # ── banner_templates.category ────────────────────────────────────────────
    op.add_column(
        'banner_templates',
        sa.Column(
            'category', sa.String(length=32), nullable=False, server_default='performance'
        ),
    )
    # Backfill: the messaging template into its own family; everything else stays
    # "performance" (the server_default).
    op.get_bind().execute(
        sa.text("UPDATE banner_templates SET category = 'messaging' WHERE name = :name"),
        {"name": _MESSAGING_NAME},
    )

    # ── briefs.banner_category (the PL's choice) ─────────────────────────────
    op.add_column('briefs', sa.Column('banner_category', sa.String(length=32), nullable=True))
    op.create_index(
        op.f('ix_briefs_banner_category'), 'briefs', ['banner_category'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_briefs_banner_category'), table_name='briefs')
    op.drop_column('briefs', 'banner_category')
    op.drop_column('banner_templates', 'category')
