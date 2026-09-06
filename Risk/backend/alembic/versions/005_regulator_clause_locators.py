"""Add source-document locator columns to regulator_clauses

Revision ID: 005
Revises: 004
Create Date: 2026-06-23

Schema-only migration. Up to now, clause *content* for regulator_clauses was
hand-typed paraphrase baked directly into migration files (003, 004) — no
link back to the actual page/paragraph in the source PDF, and no way to tell
RBI's NBFC Directions apart from its Payments Banks Directions (both just
land as regulator="RBI").

From here on, alembic stays schema-only. Clause content is produced by
parsing the real source PDFs (app/scripts/regulation_ingest/) and loaded via
a standalone script (app/scripts/regulation_ingest/load_clauses.py), not a
migration — see that script's docstring for the ingestion command. This
migration just adds the columns that ingestion needs to populate:

  - instrument: which specific regulation within a regulator, e.g. "NBFC",
    "PAYMENTS_BANK", "IA". Lets RBI's two outsourcing directions coexist
    without collapsing into one undifferentiated bucket.
  - source_doc: human-readable title of the source document, for citation.
  - page_no / para_no: where in the source PDF this clause's text came
    from, so evidence can cite an exact line instead of just a clause_ref
    string.

Existing v1/v2 rows (migrations 003/004) are left with these columns NULL —
they predate verbatim+locator tracking and aren't worth backfilling by hand;
a future "v3" load_clauses.py run supersedes them as the active version.
"""
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("regulator_clauses", sa.Column("instrument", sa.String(64), nullable=True))
    op.add_column("regulator_clauses", sa.Column("source_doc", sa.String(256), nullable=True))
    op.add_column("regulator_clauses", sa.Column("page_no", sa.Integer(), nullable=True))
    op.add_column("regulator_clauses", sa.Column("para_no", sa.String(32), nullable=True))
    op.create_index(
        "ix_regulator_clauses_regulator_instrument",
        "regulator_clauses",
        ["regulator", "instrument"],
    )


def downgrade() -> None:
    op.drop_index("ix_regulator_clauses_regulator_instrument", table_name="regulator_clauses")
    op.drop_column("regulator_clauses", "para_no")
    op.drop_column("regulator_clauses", "page_no")
    op.drop_column("regulator_clauses", "source_doc")
    op.drop_column("regulator_clauses", "instrument")
