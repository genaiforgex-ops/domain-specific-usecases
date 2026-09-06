"""performance template — generate heroes at 16:9

Switches the "Performance creatives" template's hero-image aspect ratio from 1:1
to 16:9, matching the messaging template. Only banner_templates.image_aspect
changes for that row; the resolution tier and layout are untouched.

Revision ID: a7c9e1b3d5f7
Revises: c5d6e7f8a9b0
Create Date: 2026-08-18 12:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c9e1b3d5f7'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME = "Performance creatives"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE banner_templates SET image_aspect = :a WHERE name = :n"),
        {"a": "16:9", "n": _NAME},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE banner_templates SET image_aspect = :a WHERE name = :n"),
        {"a": "1:1", "n": _NAME},
    )
