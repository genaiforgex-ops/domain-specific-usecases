"""Form engine + user role rename

Revision ID: 013
Revises: 012
Create Date: 2026-08-11

Adds form_templates, form_assignments, form_submissions for dynamic VDD forms.
Renames legacy risk_manager role slug to user.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE user_roles SET role = 'user' WHERE role = 'risk_manager'")

    op.create_table(
        "form_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "form_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("form_templates.id"), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("classification_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classification_jobs.id"), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="assigned"),
        sa.Column("draft_answers", postgresql.JSONB(), nullable=True),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_form_assignments_assignee_id", "form_assignments", ["assignee_id"])
    op.create_index("ix_form_assignments_status", "form_assignments", ["status"])

    op.create_table(
        "form_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("form_assignments.id"), nullable=False, unique=True),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("form_submissions")
    op.drop_index("ix_form_assignments_status", table_name="form_assignments")
    op.drop_index("ix_form_assignments_assignee_id", table_name="form_assignments")
    op.drop_table("form_assignments")
    op.drop_table("form_templates")
    op.execute("UPDATE user_roles SET role = 'risk_manager' WHERE role = 'user'")
