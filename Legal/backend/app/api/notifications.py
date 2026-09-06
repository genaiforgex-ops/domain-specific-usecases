"""Notification preferences + history API.

Every authenticated user manages their own settings and views their own
notification history. No special permission required.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    NotificationOut,
    NotificationSettingsOut,
    NotificationSettingsUpdate,
)
from app.services.notification_service import get_or_create_notification_settings

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/settings", response_model=NotificationSettingsOut)
def get_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationSettingsOut:
    row = get_or_create_notification_settings(db, user.id)
    db.commit()
    return NotificationSettingsOut.model_validate(row)


@router.patch("/settings", response_model=NotificationSettingsOut)
def update_settings(
    payload: NotificationSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationSettingsOut:
    row = get_or_create_notification_settings(db, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return NotificationSettingsOut.model_validate(row)


@router.get("", response_model=list[NotificationOut])
def my_notifications(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    rows = (
        db.execute(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.id.desc())
            .limit(min(limit, 100))
        )
        .scalars()
        .all()
    )
    return [NotificationOut.model_validate(r) for r in rows]
