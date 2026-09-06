from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.audit import AuditEvent
from app.models.classification import ClassificationJob
from app.models.notification import Notification
from app.models.project import Project
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.common import ORMBase

router = APIRouter(tags=["cross-cutting"])


class AuditEventResponse(ORMBase):
    id: UUID
    event_type: str
    entity_type: str
    entity_id: str
    actor_id: UUID | None
    actor_email: str | None = None
    payload_json: dict | None
    created_at: datetime


class NotificationResponse(ORMBase):
    id: UUID
    title: str
    body: str | None
    link: str | None
    is_read: bool
    created_at: datetime


def _contains(column, needle: str):
    """Case-insensitive substring match on an audit column.

    These two filters back free-text search boxes, so they have to behave like
    search: exact equality meant "login" missed `login_failed`, "AI" missed
    `ai.invocation` on case alone, and every partial word a user typed on the
    way to a full value returned nothing.

    LIKE metacharacters in the input are escaped rather than honoured — the
    values themselves contain underscores (`dd_report`, `regulation_document`),
    where an unescaped `_` is a single-character wildcard, and a stray `%` would
    silently match every row.
    """
    escaped = needle.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


@router.get("/audit", response_model=list[AuditEventResponse])
async def list_audit(
    entity_type: str | None = None,
    event_type: str | None = None,
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if entity_type and entity_type.strip():
        stmt = stmt.where(_contains(AuditEvent.entity_type, entity_type))
    if event_type and event_type.strip():
        stmt = stmt.where(_contains(AuditEvent.event_type, event_type))
    result = await db.execute(stmt)
    events = result.scalars().all()

    # Resolve actor_id -> email in a single lookup so the log is human-readable.
    actor_ids = {e.actor_id for e in events if e.actor_id}
    emails: dict = {}
    if actor_ids:
        rows = await db.execute(select(User.id, User.email).where(User.id.in_(actor_ids)))
        emails = {uid: email for uid, email in rows.all()}

    return [
        AuditEventResponse(
            id=e.id,
            event_type=e.event_type,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            actor_id=e.actor_id,
            actor_email=emails.get(e.actor_id),
            payload_json=e.payload_json,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications:read")),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("search:read")),
):
    pattern = f"%{q}%"
    vendors = await db.execute(
        select(Vendor.id, Vendor.legal_name).where(Vendor.legal_name.ilike(pattern)).limit(10)
    )
    projects = await db.execute(
        select(Project.id, Project.name).where(Project.name.ilike(pattern)).limit(10)
    )
    classifications = await db.execute(
        select(ClassificationJob.id, ClassificationJob.final_label, ClassificationJob.ai_label)
        .where(
            or_(
                ClassificationJob.final_label.ilike(pattern),
                ClassificationJob.ai_label.ilike(pattern),
            )
        )
        .limit(10)
    )
    return {
        "vendors": [{"id": str(r[0]), "name": r[1], "type": "vendor"} for r in vendors.all()],
        "projects": [{"id": str(r[0]), "name": r[1], "type": "project"} for r in projects.all()],
        "classifications": [
            {"id": str(r[0]), "label": r[1] or r[2], "type": "classification"} for r in classifications.all()
        ],
    }
