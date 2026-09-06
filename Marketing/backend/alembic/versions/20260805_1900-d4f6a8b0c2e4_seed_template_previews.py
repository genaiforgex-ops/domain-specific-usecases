"""seed the two sample template artworks

The Designer picks a banner template by looking at a rendered sample of it, so the
two built-in templates ship with their artwork:

  * assets/templates/performance_default.png — the default performance static
    (1200×1200: dot ribbon + logo lockup, rounded hero, headline/body/CTA stack).
  * assets/templates/wa_rcs_rpn.png — the WhatsApp / RCS / RPN messaging banner
    (1440×720: full-bleed photo, copy set over the left third).

Each is written onto the *built-in* template of its category, and only when that
template has no artwork yet — so an Admin's own upload is never overwritten, and
templates added to a category later don't inherit these samples. A missing asset
file is skipped rather than failing the migration (the artwork is cosmetic; the
picker falls back to a text-only card).

Revision ID: d4f6a8b0c2e4
Revises: c3e5f7a9b1d4
Create Date: 2026-08-05 19:00:00.000000
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f6a8b0c2e4'
down_revision: Union[str, None] = 'c3e5f7a9b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# backend/alembic/versions/<this file> → backend/assets/templates
_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "templates"

# category → the sample artwork for that category's built-in template
_SAMPLES = {
    "performance": "performance_default.png",
    "messaging": "wa_rcs_rpn.png",
}

_CATEGORIES = tuple(_SAMPLES)


def _templates_table() -> sa.Table:
    """Just the columns this migration touches — never the live ORM model."""
    return sa.table(
        "banner_templates",
        sa.column("category", sa.String),
        sa.column("is_builtin", sa.Boolean),
        sa.column("preview_image", sa.LargeBinary),
        sa.column("preview_mime", sa.String),
    )


def upgrade() -> None:
    tbl = _templates_table()
    bind = op.get_bind()
    for category, filename in _SAMPLES.items():
        path = _ASSETS / filename
        if not path.is_file():
            print(f"[template previews] skipped {category}: {path} is missing")
            continue
        bind.execute(
            tbl.update()
            .where(
                tbl.c.category == category,
                tbl.c.is_builtin.is_(True),
                tbl.c.preview_image.is_(None),
            )
            .values(preview_image=path.read_bytes(), preview_mime="image/png")
        )


def downgrade() -> None:
    tbl = _templates_table()
    op.get_bind().execute(
        tbl.update()
        .where(tbl.c.category.in_(_CATEGORIES), tbl.c.is_builtin.is_(True))
        .values(preview_image=None, preview_mime=None)
    )
