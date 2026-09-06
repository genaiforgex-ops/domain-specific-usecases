"""drop business_unit; automatic brief dates; per-brief copy prompt

Three changes to `briefs`, all driven by the Product Lead's intake feedback:

  * **business_unit dropped** — no longer required for business operations, so it
    leaves the template, the agent's extraction schema and the search filters too.
  * **expected_date added** — neither date is typed in any more. `brief_date` is
    the day the brief was raised and `expected_date` follows it by
    brief_service.EXPECTED_TURNAROUND_DAYS (3). Backfilled here for existing rows,
    using created_at where a brief never got a date at all.
  * **copy_prompt added** — the brief's own (individual-level) copy direction,
    layered under the author's / Copywriter's standing Prompt Studio prompts at
    generation time.

Revision ID: e5a7c9b1d3f6
Revises: d4f6a8b0c2e4
Create Date: 2026-08-06 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5a7c9b1d3f6'
down_revision: Union[str, None] = 'd4f6a8b0c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TURNAROUND_DAYS = 3


def upgrade() -> None:
    bind = op.get_bind()

    # ── The two automatic dates ──────────────────────────────────────────────
    op.add_column('briefs', sa.Column('expected_date', sa.Date(), nullable=True))
    # Older briefs may never have had a date typed in — fall back to the day the
    # row was created, so every brief now carries both dates.
    bind.execute(sa.text("UPDATE briefs SET brief_date = created_at::date WHERE brief_date IS NULL"))
    # In Postgres `date + integer` is a date — exactly the +3 days rule. The day
    # count is our own int constant, so it goes in as a literal (a bind param here
    # would leave the operator's right-hand type ambiguous).
    bind.execute(sa.text(f"UPDATE briefs SET expected_date = brief_date + {_TURNAROUND_DAYS}"))

    # ── This brief's own copy direction ──────────────────────────────────────
    op.add_column('briefs', sa.Column('copy_prompt', sa.Text(), nullable=True))

    # ── Business Unit retired ────────────────────────────────────────────────
    op.drop_column('briefs', 'business_unit')


def downgrade() -> None:
    op.add_column('briefs', sa.Column('business_unit', sa.String(length=255), nullable=True))
    op.drop_column('briefs', 'copy_prompt')
    op.drop_column('briefs', 'expected_date')
