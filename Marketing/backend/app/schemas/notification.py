"""Notification DTOs — a per-user feed derived from brief events."""

import uuid

from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    """One notification: a brief event made relevant to the signed-in user."""

    id: uuid.UUID  # the underlying brief event id
    brief_id: uuid.UUID
    brief_title: str
    kind: str
    title: str  # friendly headline, e.g. "Brief approved"
    body: str  # the event's human action phrase
    actor_name: str
    actor_role: str
    at: datetime
    read: bool


class NotificationFeed(BaseModel):
    items: list[NotificationOut]
    unread_count: int
