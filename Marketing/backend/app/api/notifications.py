"""Notification routes — the per-user feed and a mark-all-seen action."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.notification import NotificationFeed, NotificationOut
from app.services import notification_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationFeed)
def list_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationFeed:
    events, unread = notification_service.get_feed(db, user)
    items = [
        NotificationOut(
            id=e.id,
            brief_id=e.brief_id,
            brief_title=(e.brief.project_name or e.brief.product_name or "Untitled brief"),
            kind=e.kind,
            title=notification_service.title_for(e.kind),
            body=e.action,
            actor_name=e.actor_name,
            actor_role=e.actor_role,
            at=e.at,
            read=notification_service.is_read(e, user),
        )
        for e in events
    ]
    return NotificationFeed(items=items, unread_count=unread)


@router.post("/seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    notification_service.mark_seen(db, user)
