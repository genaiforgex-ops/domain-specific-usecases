"""DTOs for notification preferences and history."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_enabled: bool
    chat_share: bool
    msa_share: bool
    task_assigned: bool
    approvals: bool
    msa_updates: bool


class NotificationSettingsUpdate(BaseModel):
    email_enabled: bool | None = None
    chat_share: bool | None = None
    msa_share: bool | None = None
    task_assigned: bool | None = None
    approvals: bool | None = None
    msa_updates: bool | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    subject: str
    status: str
    created_at: datetime
    sent_at: datetime | None = None
