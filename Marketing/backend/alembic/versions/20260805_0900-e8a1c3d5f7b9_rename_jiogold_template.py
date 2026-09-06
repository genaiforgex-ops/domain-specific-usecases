"""rename the JioGold template to "Performance creatives"

Renames the built-in "JioGold — On-brand" banner template to "Performance
creatives" (its name in the template picker / Prompt Studio) and refreshes its
description to match. Layout and all other fields are unchanged.

Revision ID: e8a1c3d5f7b9
Revises: d7f9a1b3c5e7
Create Date: 2026-08-05 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8a1c3d5f7b9'
down_revision: Union[str, None] = 'd7f9a1b3c5e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "JioGold — On-brand"
_NEW = "Performance creatives"
_DESCRIPTION = (
    "On-brand performance-ad creatives: Reliance-navy background, JioDot brand strip "
    "with the official JioFinance logo lockup, JioType headline/body, gold pill CTA and "
    "footer, across the five ad sizes."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE banner_templates SET name = :new, description = :desc WHERE name = :old"),
        {"new": _NEW, "desc": _DESCRIPTION, "old": _OLD},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE banner_templates SET name = :old WHERE name = :new"),
        {"old": _OLD, "new": _NEW},
    )
