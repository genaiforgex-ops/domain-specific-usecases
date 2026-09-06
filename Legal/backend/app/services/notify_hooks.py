"""Event → notification helpers.

One function per domain event. Each builds the template and enqueues (an INSERT
in the caller's transaction), wrapped in try/except so a notification never
breaks the triggering action. Import and call these right beside the existing
`write_audit(...)` at each event site.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Permission, Role, has_permission
from app.models.notification import (
    CATEGORY_APPROVALS,
    CATEGORY_CHAT_SHARE,
    CATEGORY_MSA_SHARE,
    CATEGORY_MSA_UPDATES,
    CATEGORY_REGULATORY,
    CATEGORY_TASK_ASSIGNED,
)
from app.models.user import User
from app.services import notification_templates as tpl
from app.services.notification_service import get_notification_service

logger = logging.getLogger("legalos.notifications")


def _first_name(u: User) -> str:
    return (u.full_name or u.email or "there").split(" ")[0]


def _safe(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001 — a notification must never break the action
        logger.exception("notification hook failed")


def approver_pool(db: Session) -> list[User]:
    """Active users whose role grants APPROVE_AI_OUTPUT."""
    approver_roles = [r for r in Role if has_permission(r, Permission.APPROVE_AI_OUTPUT)]
    role_values = [r.value for r in approver_roles]
    if not role_values:
        return []
    return (
        db.execute(select(User).where(User.is_active.is_(True), User.role.in_(role_values)))
        .scalars()
        .all()
    )


def notify_chat_shared(db: Session, recipient: User, owner_name: str, chat_title: str, session_id: str) -> None:
    def _do():
        subject, html, text = tpl.chat_shared(_first_name(recipient), owner_name, chat_title)
        get_notification_service().enqueue(
            db, user=recipient, category=CATEGORY_CHAT_SHARE, subject=subject,
            body_html=html, body_text=text, related_type="chat_session", related_id=session_id,
        )
    _safe(_do)


def notify_msa_shared(db: Session, recipient: User, sharer_name: str, vendor: str, tracker_id: int, access: str) -> None:
    def _do():
        subject, html, text = tpl.msa_shared(_first_name(recipient), sharer_name, vendor, tracker_id, access)
        get_notification_service().enqueue(
            db, user=recipient, category=CATEGORY_MSA_SHARE, subject=subject,
            body_html=html, body_text=text, related_type="msa_tracker", related_id=tracker_id,
        )
    _safe(_do)


def notify_task_assigned(db: Session, assignee: User, assigner_name: str, task_title: str, due: str | None, task_id: int) -> None:
    def _do():
        subject, html, text = tpl.task_assigned(_first_name(assignee), assigner_name, task_title, due)
        get_notification_service().enqueue(
            db, user=assignee, category=CATEGORY_TASK_ASSIGNED, subject=subject,
            body_html=html, body_text=text, related_type="task", related_id=task_id,
        )
    _safe(_do)


def notify_approval_escalation(db: Session, question: str, query_id: int) -> None:
    def _do():
        for approver in approver_pool(db):
            subject, html, text = tpl.approval_escalation(_first_name(approver), question)
            get_notification_service().enqueue(
                db, user=approver, category=CATEGORY_APPROVALS, subject=subject,
                body_html=html, body_text=text, related_type="legal_bot_query", related_id=query_id,
            )
    _safe(_do)


def notify_approval_resolved(db: Session, asker: User, question: str, query_id: int) -> None:
    def _do():
        subject, html, text = tpl.approval_resolved(_first_name(asker), question)
        get_notification_service().enqueue(
            db, user=asker, category=CATEGORY_APPROVALS, subject=subject,
            body_html=html, body_text=text, related_type="legal_bot_query", related_id=query_id,
        )
    _safe(_do)


def notify_msa_vendor_ingested(db: Session, user: User, vendor: str, tracker_id: int) -> None:
    def _do():
        subject, html, text = tpl.msa_vendor_ingested(_first_name(user), vendor, tracker_id)
        get_notification_service().enqueue(
            db, user=user, category=CATEGORY_MSA_UPDATES, subject=subject,
            body_html=html, body_text=text, related_type="msa_tracker", related_id=tracker_id,
        )
    _safe(_do)


def _legal_news_recipients(db: Session) -> list[User]:
    """Active users whose role grants LEGAL_NEWS_FULL."""
    roles = [r for r in Role if has_permission(r, Permission.LEGAL_NEWS_FULL)]
    role_values = [r.value for r in roles]
    if not role_values:
        return []
    return (
        db.execute(select(User).where(User.is_active.is_(True), User.role.in_(role_values)))
        .scalars()
        .all()
    )


def notify_regulatory_updates(db: Session, items) -> None:
    """Email the legal team a digest of new action-required regulatory updates.

    `items` is a list of RegulatoryUpdate objects (uses .source and .title).
    """
    def _do():
        recipients = _legal_news_recipients(db)
        if not recipients:
            return
        pairs = [(getattr(i, "source", "") or "Regulator", getattr(i, "title", "")) for i in items]
        svc = get_notification_service()
        for r in recipients:
            subject, html, text = tpl.regulatory_alert(_first_name(r), pairs)
            svc.enqueue(
                db, user=r, category=CATEGORY_REGULATORY, subject=subject,
                body_html=html, body_text=text, related_type="regulatory", related_id=None,
            )
    _safe(_do)


def notify_msa_executed(db: Session, recipients: list[User], vendor: str, tracker_id: int) -> None:
    def _do():
        svc = get_notification_service()
        seen: set[int] = set()
        for r in recipients:
            if r is None or r.id in seen:
                continue
            seen.add(r.id)
            subject, html, text = tpl.msa_executed(_first_name(r), vendor, tracker_id)
            svc.enqueue(
                db, user=r, category=CATEGORY_MSA_UPDATES, subject=subject,
                body_html=html, body_text=text, related_type="msa_tracker", related_id=tracker_id,
            )
    _safe(_do)
