"""M1 classification agents (user-authored prompt configs)

Revision ID: 008
Revises: 007
Create Date: 2026-07-24

Adds the ability to save multiple named "agents" for the M1 use case, each a
self-contained prompt configuration (separate RBI/SEBI guidance + model +
temperature). A classification run can select one or more agents; each runs and
records a classification_agent_runs row so the Review screen can show the
results side-by-side.

classification_jobs gets agent_ids (JSONB) — the agents chosen for that job.
Null/empty preserves the existing built-in default run exactly, so every job
created before this migration keeps classifying unchanged.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classification_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rbi_prompt", sa.Text(), nullable=False),
        sa.Column("sebi_prompt", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False, server_default="gemini-2.5-flash"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_classification_agents_is_active", "classification_agents", ["is_active"])

    op.create_table(
        "classification_agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classification_jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classification_agents.id"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("rbi_label", sa.String(64), nullable=True),
        sa.Column("rbi_confidence", sa.Float(), nullable=True),
        sa.Column("rbi_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("sebi_label", sa.String(64), nullable=True),
        sa.Column("sebi_confidence", sa.Float(), nullable=True),
        sa.Column("sebi_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("agent_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_classification_agent_runs_job_id", "classification_agent_runs", ["job_id"])

    op.add_column("classification_jobs", sa.Column("agent_ids", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("classification_jobs", "agent_ids")
    op.drop_index("ix_classification_agent_runs_job_id", table_name="classification_agent_runs")
    op.drop_table("classification_agent_runs")
    op.drop_index("ix_classification_agents_is_active", table_name="classification_agents")
    op.drop_table("classification_agents")
