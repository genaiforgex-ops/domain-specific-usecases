"""Link email drafts to tasks and flag auto-generated drafts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def _email_draft_columns(inspector) -> set[str]:
    return {col["name"] for col in inspector.get_columns("email_drafts")}


def _email_draft_index_names(inspector) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes("email_drafts")}


def _has_task_fk(inspector) -> bool:
    for fk in inspector.get_foreign_keys("email_drafts"):
        if fk.get("referred_table") == "tasks" and "task_id" in fk.get("constrained_columns", []):
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = _email_draft_columns(inspector)

    if "task_id" not in columns:
        op.add_column(
            "email_drafts",
            sa.Column("task_id", sa.Integer(), nullable=True),
        )
        columns.add("task_id")

    if "auto_generated" not in columns:
        op.add_column(
            "email_drafts",
            sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default="false"),
        )

    inspector = inspect(bind)
    if "ix_email_drafts_task_id" not in _email_draft_index_names(inspector):
        op.create_index("ix_email_drafts_task_id", "email_drafts", ["task_id"])

    inspector = inspect(bind)
    if not _has_task_fk(inspector):
        op.create_foreign_key(
            "fk_email_drafts_task_id_tasks",
            "email_drafts",
            "tasks",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_task_fk(inspector):
        op.drop_constraint("fk_email_drafts_task_id_tasks", "email_drafts", type_="foreignkey")

    if "ix_email_drafts_task_id" in _email_draft_index_names(inspector):
        op.drop_index("ix_email_drafts_task_id", table_name="email_drafts")

    columns = _email_draft_columns(inspector)
    if "auto_generated" in columns:
        op.drop_column("email_drafts", "auto_generated")
    if "task_id" in columns:
        op.drop_column("email_drafts", "task_id")
