"""banner template image_brief + messaging copy-side flip

Adds the `image_brief` column (hero-photo art-direction fed to the image model so
the generated subject leaves the template's copy area clear) and backfills both
built-in templates. Also refreshes the messaging template's render program and
brand to the copy-on-the-right / subject-on-the-left layout.

Revision ID: f3b2c5d7e9a1
Revises: e2a1b4c6d8f0
Create Date: 2026-08-04 15:00:00.000000
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3b2c5d7e9a1'
down_revision: Union[str, None] = 'e2a1b4c6d8f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JIOGOLD = "JioGold — On-brand"
_MESSAGING = "Messaging — WhatsApp / RCS / RPN"


def upgrade() -> None:
    op.add_column(
        'banner_templates',
        sa.Column('image_brief', sa.Text(), nullable=False, server_default=''),
    )

    from app.services.figma import render

    jg = render.builtin_bundle()
    msg = render.messaging_bundle()
    bind = op.get_bind()

    # JioGold: just backfill its hero-photo brief (render program unchanged).
    bind.execute(
        sa.text("UPDATE banner_templates SET image_brief = :brief WHERE name = :name"),
        {"brief": jg.image_brief, "name": _JIOGOLD},
    )
    # Messaging: backfill the brief AND re-sync the render program + brand, which now
    # place the copy on the right (subject composed on the left).
    bind.execute(
        sa.text(
            """
            UPDATE banner_templates
               SET image_brief = :brief,
                   js_body = :js_body,
                   brand = CAST(:brand AS JSONB)
             WHERE name = :name
            """
        ),
        {
            "brief": msg.image_brief,
            "js_body": msg.js_body,
            "brand": json.dumps(msg.brand),
            "name": _MESSAGING,
        },
    )


def downgrade() -> None:
    op.drop_column('banner_templates', 'image_brief')
