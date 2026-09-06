"""banner template image aspect/size — real image-model output params

Adds image_aspect (Gemini aspect ratio) and image_size (1K/2K/4K) to banner
templates so hero images are generated at the right shape per format instead of
being coaxed via prompt text. Backfills JioGold = 1:1 (one hero centre-cropped into
five shapes) and Messaging = 16:9 (WA/RCS/RPN are all wide).

Revision ID: c6e8f0a2b4d6
Revises: b5d7f9a1c3e5
Create Date: 2026-08-04 21:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6e8f0a2b4d6'
down_revision: Union[str, None] = 'b5d7f9a1c3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JIOGOLD = "JioGold — On-brand"
_MESSAGING = "Messaging — WhatsApp / RCS / RPN"


def upgrade() -> None:
    op.add_column('banner_templates', sa.Column('image_aspect', sa.String(length=8), nullable=False, server_default=''))
    op.add_column('banner_templates', sa.Column('image_size', sa.String(length=4), nullable=False, server_default=''))
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE banner_templates SET image_aspect = :a WHERE name = :n"),
        {"a": "1:1", "n": _JIOGOLD},
    )
    bind.execute(
        sa.text("UPDATE banner_templates SET image_aspect = :a WHERE name = :n"),
        {"a": "16:9", "n": _MESSAGING},
    )


def downgrade() -> None:
    op.drop_column('banner_templates', 'image_size')
    op.drop_column('banner_templates', 'image_aspect')
