"""performance template — rebrand Figma frame/header names

Re-syncs the "Performance creatives" template's render program so the frames it
draws in Figma are named "Performance / …" (and the page header reads "Performance
creatives …") instead of "JioGold / …". Only js_body changes.

Revision ID: f9b2d4c6e8a0
Revises: e8a1c3d5f7b9
Create Date: 2026-08-05 11:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f9b2d4c6e8a0'
down_revision: Union[str, None] = 'e8a1c3d5f7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME = "Performance creatives"


def upgrade() -> None:
    from app.services.figma import render

    op.get_bind().execute(
        sa.text("UPDATE banner_templates SET js_body = :js WHERE name = :name"),
        {"js": render.builtin_bundle().js_body, "name": _NAME},
    )


def downgrade() -> None:
    # One-way: the old js_body carried the "JioGold /" frame names.
    pass
