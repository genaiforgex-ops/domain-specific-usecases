"""Regulatory Intelligence: tracked sources + update source/category + regulatory alerts."""

from alembic import op
import sqlalchemy as sa

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracked_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("regulator", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="web"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=255), nullable=True),
        sa.Column("added_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["added_by_id"], ["users.id"]),
    )

    op.add_column("regulatory_updates", sa.Column("source_id", sa.Integer(), nullable=True))
    op.add_column("regulatory_updates", sa.Column("category", sa.String(length=64), nullable=True))
    op.create_index("ix_regulatory_updates_source_id", "regulatory_updates", ["source_id"])
    op.create_index("ix_regulatory_updates_category", "regulatory_updates", ["category"])
    op.create_foreign_key(
        "fk_regulatory_updates_source_id",
        "regulatory_updates",
        "tracked_sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "notification_settings",
        sa.Column("regulatory", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "regulatory")
    op.drop_constraint("fk_regulatory_updates_source_id", "regulatory_updates", type_="foreignkey")
    op.drop_index("ix_regulatory_updates_category", table_name="regulatory_updates")
    op.drop_index("ix_regulatory_updates_source_id", table_name="regulatory_updates")
    op.drop_column("regulatory_updates", "category")
    op.drop_column("regulatory_updates", "source_id")
    op.drop_table("tracked_sources")
