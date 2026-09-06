"""Email-notification persistence.

`Notification` is a transactional **outbox**: domain events insert a row (in the
same DB transaction as the event) and a background worker later sends it over
SMTP. This decouples email delivery from the request path — an SMTP outage never
rolls back or slows the action that triggered the notification, and nothing is
lost (rows are retried until sent or exhausted).

`NotificationSetting` is a per-user 1:1 preferences row (mirrors GmailSettings),
consulted before a notification is enqueued.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Category keys — kept in one place so hooks, prefs, and templates agree.
CATEGORY_CHAT_SHARE = "chat_share"
CATEGORY_MSA_SHARE = "msa_share"
CATEGORY_TASK_ASSIGNED = "task_assigned"
CATEGORY_APPROVALS = "approvals"
CATEGORY_MSA_UPDATES = "msa_updates"
CATEGORY_REGULATORY = "regulatory"

# Maps a category to the NotificationSetting boolean column that gates it.
CATEGORY_PREF_FIELD = {
    CATEGORY_CHAT_SHARE: "chat_share",
    CATEGORY_MSA_SHARE: "msa_share",
    CATEGORY_TASK_ASSIGNED: "task_assigned",
    CATEGORY_APPROVALS: "approvals",
    CATEGORY_MSA_UPDATES: "msa_updates",
    CATEGORY_REGULATORY: "regulatory",
}


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationSetting(Base):
    """Per-user email-notification preferences. Defaults: everything on."""

    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    chat_share: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    msa_share: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    task_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approvals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    msa_updates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    regulatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
