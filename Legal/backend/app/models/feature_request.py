from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FeatureRequest(Base):
    """A user-submitted feature request or bug report.

    Auto-progressed through an agent pipeline:
      submitted → analysing → planning → in_progress → pr_open
      (manual gate: human approves PR)
      → in_review → merged → deploying → deployed
    Failure terminals: rejected, failed.
    """

    __tablename__ = "feature_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False, default="feature")
    priority: Mapped[str] = mapped_column(String(4), nullable=False, default="P2")
    priority_score: Mapped[float] = mapped_column(nullable=False, default=0.0)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")

    repository: Mapped[str | None] = mapped_column(String(256), nullable=True)
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_issue_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    deployment_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    plan: Mapped[list | None] = mapped_column(JSON, nullable=True)
    files_touched: Mapped[list | None] = mapped_column(JSON, nullable=True)
    loc_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    pr_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
