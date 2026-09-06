"""messaging banner template — WhatsApp / RCS / RPN

Seeds the messaging-formats banner template (full-bleed hero + scrim, sizes WA /
RCS / RPN) as a non-default built-in, so the Designer can pick it in the export
step alongside the default JioGold performance template.

Revision ID: e2a1b4c6d8f0
Revises: d1f0a2b3c4d5
Create Date: 2026-08-04 13:00:00.000000
"""
import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2a1b4c6d8f0'
down_revision: Union[str, None] = 'd1f0a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME = "Messaging — WhatsApp / RCS / RPN"


def upgrade() -> None:
    # Seed from the render module's canonical messaging definition (brand system,
    # sizes, render program). Non-default so the JioGold template stays the default.
    from app.services.figma import render

    b = render.messaging_bundle()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO banner_templates
              (id, name, description, js_body, brand, sizes, footer_left, footer_right,
               strips, is_default, is_builtin, created_at, updated_at)
            VALUES
              (:id, :name, :description, :js_body,
               CAST(:brand AS JSONB), CAST(:sizes AS JSONB), :footer_left, :footer_right,
               CAST(:strips AS JSONB), false, true, now(), now())
            ON CONFLICT (name) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "name": _NAME,
            "description": (
                "Messaging-format banners for WhatsApp, RCS and Rich Push Notification: "
                "a full-bleed lifestyle hero photo with a left dark-to-transparent scrim, "
                "JioType Black headline, Regular body line and a small terms footer."
            ),
            "js_body": b.js_body,
            "brand": json.dumps(b.brand),
            "sizes": json.dumps(b.sizes),
            "footer_left": b.footer_left,
            "footer_right": b.footer_right,
            "strips": json.dumps(b.strips),
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM banner_templates WHERE name = :name"), {"name": _NAME}
    )
