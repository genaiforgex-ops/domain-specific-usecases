"""banner templates — DB-backed gallery of on-brand banner designs

Creates the banner_templates table and seeds the built-in JioGold template as the
default, so the Figma export reads its render inputs (brand system, sizes, strips,
render program) from the DB instead of module constants.

Revision ID: d1f0a2b3c4d5
Revises: c9e3a5b7d1f8
Create Date: 2026-07-28 12:00:00.000000
"""
import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1f0a2b3c4d5'
down_revision: Union[str, None] = 'c9e3a5b7d1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'banner_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('js_body', sa.Text(), nullable=False),
        sa.Column('brand', postgresql.JSONB(), nullable=False),
        sa.Column('sizes', postgresql.JSONB(), nullable=False),
        sa.Column('footer_left', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('footer_right', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('strips', postgresql.JSONB(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Seed the built-in JioGold template from the render module's canonical
    # definition (brand system, sizes, strip SVGs, render program).
    from app.services.figma import render

    b = render.builtin_bundle()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO banner_templates
              (id, name, description, js_body, brand, sizes, footer_left, footer_right,
               strips, is_default, is_builtin, created_at, updated_at)
            VALUES
              (:id, :name, :description, :js_body,
               CAST(:brand AS JSONB), CAST(:sizes AS JSONB), :footer_left, :footer_right,
               CAST(:strips AS JSONB), true, true, now(), now())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "name": "JioGold — On-brand",
            "description": (
                "The on-brand JioGold performance-ad template: Reliance-navy background, "
                "JioDot brand strip with the official logo lockup, JioType headline/body, "
                "gold pill CTA and footer, across the five ad sizes."
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
    op.drop_table('banner_templates')
