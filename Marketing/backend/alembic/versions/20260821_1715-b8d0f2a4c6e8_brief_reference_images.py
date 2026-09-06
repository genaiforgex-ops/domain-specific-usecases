"""brief reference images

Sample copies / examples the Product Lead attaches to a brief so everyone down the
chain can see the visual references. One row per attached image; PNG bytes live in
the row (served through a dedicated content endpoint), matching the Designer's
banner-image storage. Cascades with the brief.

Revision ID: b8d0f2a4c6e8
Revises: a7c9e1b3d5f7
Create Date: 2026-08-21 17:15:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8d0f2a4c6e8'
down_revision: Union[str, None] = 'a7c9e1b3d5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'brief_reference_images',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('brief_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('mime_type', sa.String(length=64), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_by_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('uploaded_by_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['brief_id'], ['briefs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_brief_reference_images_brief_id'),
        'brief_reference_images',
        ['brief_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_brief_reference_images_brief_id'), table_name='brief_reference_images'
    )
    op.drop_table('brief_reference_images')
