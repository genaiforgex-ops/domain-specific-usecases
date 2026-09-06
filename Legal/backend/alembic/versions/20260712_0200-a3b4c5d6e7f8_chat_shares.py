"""Chat sharing: sessions shared read-only with other users."""

from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("shared_by_user_id", sa.Integer(), nullable=False),
        sa.Column("shared_with_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["shared_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["shared_with_user_id"], ["users.id"]),
        sa.UniqueConstraint("session_id", "shared_with_user_id", name="uq_chat_share_session_user"),
    )
    op.create_index("ix_chat_shares_session_id", "chat_shares", ["session_id"])
    op.create_index("ix_chat_shares_shared_with_user_id", "chat_shares", ["shared_with_user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_shares_shared_with_user_id", table_name="chat_shares")
    op.drop_index("ix_chat_shares_session_id", table_name="chat_shares")
    op.drop_table("chat_shares")
