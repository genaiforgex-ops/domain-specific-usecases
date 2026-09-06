"""messaging template — revert copy back to the left (original layout)

Restores the messaging (WhatsApp / RCS / RPN) template to its original working
layout: copy on the LEFT, hero subject composed on the RIGHT. Re-syncs the DB row's
brand (copy_side) and image_brief from the render module. js_body is unchanged (it
branches on brand.copy_side).

Revision ID: d7f9a1b3c5e7
Revises: c6e8f0a2b4d6
Create Date: 2026-08-04 23:00:00.000000
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7f9a1b3c5e7'
down_revision: Union[str, None] = 'c6e8f0a2b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MESSAGING = "Messaging — WhatsApp / RCS / RPN"


def upgrade() -> None:
    from app.services.figma import render

    msg = render.messaging_bundle()
    op.get_bind().execute(
        sa.text(
            """
            UPDATE banner_templates
               SET brand = CAST(:brand AS JSONB),
                   image_brief = :brief,
                   js_body = :js_body
             WHERE name = :name
            """
        ),
        {
            "brand": json.dumps(msg.brand),
            "brief": msg.image_brief,
            "js_body": msg.js_body,
            "name": _MESSAGING,
        },
    )


def downgrade() -> None:
    # No-op: the previous (copy-right) values are restored by re-running the earlier
    # migrations if needed; this revert is intentionally one-way.
    pass
