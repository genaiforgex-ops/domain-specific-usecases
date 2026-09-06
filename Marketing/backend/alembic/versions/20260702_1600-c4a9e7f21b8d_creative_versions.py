"""creative versions

Revision ID: c4a9e7f21b8d
Revises: b3f7c1a9d2e4
Create Date: 2026-07-02 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a9e7f21b8d'
down_revision: Union[str, None] = 'b3f7c1a9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'creative_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('creative_id', sa.UUID(), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('visual_reference', sa.Text(), nullable=True),
        sa.Column('headline', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('cta', sa.String(length=120), nullable=False),
        sa.Column('entity_attribution', sa.Text(), nullable=True),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('editor_id', sa.UUID(), nullable=True),
        sa.Column('editor_name', sa.String(length=255), nullable=True),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['creative_id'], ['creatives.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['editor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_creative_versions_creative_id'), 'creative_versions', ['creative_id'], unique=False)

    op.add_column('creatives', sa.Column('active_version_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        None, 'creatives', 'creative_versions', ['active_version_id'], ['id'],
        ondelete='SET NULL', use_alter=True,
    )


def downgrade() -> None:
    op.drop_constraint(None, 'creatives', type_='foreignkey')
    op.drop_column('creatives', 'active_version_id')
    op.drop_index(op.f('ix_creative_versions_creative_id'), table_name='creative_versions')
    op.drop_table('creative_versions')
