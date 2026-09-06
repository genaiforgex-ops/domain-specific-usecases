"""Remove demo/seed email tasks that lack a Gmail message id."""

from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM tasks WHERE source = 'email' AND gmail_message_id IS NULL"
    )


def downgrade() -> None:
    pass
