"""Notifications — a per-user feed built from the immutable brief-event trail.

There's no separate notifications table: every meaningful state change already
writes a BriefEvent, so a user's notifications are simply the recent events on
briefs in their scope that someone *else* triggered. Unread is derived from the
user's `notifications_seen_at` mark.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.brief import Brief
from app.models.brief_event import BriefEvent
from app.models.user import User

# Scope comes from Brief.involves — a user is notified about a brief only when they
# hold one of its pipeline slots. Role alone grants no feed: an ML who isn't this
# brief's Marketing Lead has no business being told about it. Admin oversight of
# *every* brief lives on the dashboard / oversight pages, which query briefs
# directly — not here.

# Friendly headline per event kind.
_TITLES: dict[str, str] = {
    "created": "Brief created",
    "submitted": "Brief submitted",
    "approved": "Brief approved",
    "changes_requested": "Changes requested",
    "assigned": "Brief routed",
    "creatives_generated": "Copies generated",
    "copies_submitted": "Copies handed to design",
    "gate1_signoff": "Approval decision",
    "gate1_cleared": "Final sign-off complete",
    "banner_images_generated": "Banner images generated",
    "banner_image_uploaded": "Banner image replaced",
    "banner_image_edited": "Banner image edited",
    "banner_images_approved": "Banner images approved",
    "design_submitted": "Design sent for review",
    "figma_exported": "Exported to Figma",
}

_FEED_LIMIT = 30


def _scoped_query(user: User):
    """Events on this user's own briefs, newest first, excluding their own actions.

    "Their own" means they hold a slot on the brief — creator, copywriter,
    marketing, product or designer. Nothing else reaches the feed.
    """
    return (
        select(BriefEvent)
        .join(Brief, BriefEvent.brief_id == Brief.id)
        .where(Brief.involves(user.id))
        # Don't notify people about what they themselves did.
        .where((BriefEvent.actor_id != user.id) | (BriefEvent.actor_id.is_(None)))
    )


def get_feed(db: Session, user: User) -> tuple[list[BriefEvent], int]:
    """Return (recent events, unread_count) for the user's notification feed."""
    base = _scoped_query(user)

    events = list(
        db.execute(
            base.options(selectinload(BriefEvent.brief))
            .order_by(BriefEvent.at.desc())
            .limit(_FEED_LIMIT)
        ).scalars()
    )

    unread_stmt = base.with_only_columns(func.count(BriefEvent.id))
    if user.notifications_seen_at is not None:
        unread_stmt = unread_stmt.where(BriefEvent.at > user.notifications_seen_at)
    unread = db.execute(unread_stmt).scalar_one()

    return events, unread


def title_for(kind: str) -> str:
    return _TITLES.get(kind, "Update")


def is_read(event: BriefEvent, user: User) -> bool:
    return user.notifications_seen_at is not None and event.at <= user.notifications_seen_at


def mark_seen(db: Session, user: User) -> None:
    """Clear the unread badge — mark everything up to now as seen."""
    user.notifications_seen_at = datetime.now(timezone.utc)
    db.commit()
