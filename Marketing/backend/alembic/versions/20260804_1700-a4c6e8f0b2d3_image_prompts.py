"""image prompts — per-user hero-image art-direction overrides (Prompt Studio)

Creates the image_prompts table: one row per (user, banner template) holding that
user's custom art-direction for the template's hero photos. Empty by default —
generation falls back to each template's built-in image_brief.

Revision ID: a4c6e8f0b2d3
Revises: f3b2c5d7e9a1
Create Date: 2026-08-04 17:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4c6e8f0b2d3'
down_revision: Union[str, None] = 'f3b2c5d7e9a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'image_prompts',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('template_id', sa.UUID(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['banner_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'template_id'),
    )


def downgrade() -> None:
    op.drop_table('image_prompts')
