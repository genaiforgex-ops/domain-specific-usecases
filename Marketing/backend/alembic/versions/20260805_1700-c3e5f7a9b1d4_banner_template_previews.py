"""banner template previews + the Designer's template pick

Templates become *visually* pickable, and the pick is persisted:
  * banner_templates gain `preview_image` / `preview_mime` — the reference artwork
    for the template, stored as bytes in the row (like banner_images) so the
    gallery needs no media volume. NULL until an Admin uploads one.
  * briefs gain `banner_template_id` — the specific template the Designer chooses
    inside the brief's locked category, before the hero images are generated. It
    art-directs the photos and renders the Figma export, so it lives on the brief:
    a reload, a regenerate and the export all resolve to the same template.

Revision ID: c3e5f7a9b1d4
Revises: b2d4f6a8c0e2
Create Date: 2026-08-05 17:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3e5f7a9b1d4'
down_revision: Union[str, None] = 'b2d4f6a8c0e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── banner_templates: the reference artwork the Designer picks from ───────
    op.add_column('banner_templates', sa.Column('preview_image', sa.LargeBinary(), nullable=True))
    op.add_column(
        'banner_templates', sa.Column('preview_mime', sa.String(length=64), nullable=True)
    )

    # ── briefs.banner_template_id (the Designer's pick) ──────────────────────
    op.add_column(
        'briefs', sa.Column('banner_template_id', sa.UUID(as_uuid=True), nullable=True)
    )
    op.create_index(
        op.f('ix_briefs_banner_template_id'), 'briefs', ['banner_template_id'], unique=False
    )
    op.create_foreign_key(
        'fk_briefs_banner_template_id_banner_templates',
        'briefs',
        'banner_templates',
        ['banner_template_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_briefs_banner_template_id_banner_templates', 'briefs', type_='foreignkey'
    )
    op.drop_index(op.f('ix_briefs_banner_template_id'), table_name='briefs')
    op.drop_column('briefs', 'banner_template_id')
    op.drop_column('banner_templates', 'preview_mime')
    op.drop_column('banner_templates', 'preview_image')
