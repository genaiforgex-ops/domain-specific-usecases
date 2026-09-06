"""Shared email-to-task ingestion for Task Manager and Gmail poller."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.orchestrator import tasks as orch_tasks
from app.services.gmail_service import ParsedEmail


@dataclass
class IngestResult:
    tasks: list[Task]
    should_mark_processed: bool
    reason: str  # created | duplicate | no_action | empty_body


def ingest_email_as_tasks(
    db: Session,
    user: User,
    parsed: ParsedEmail,
    *,
    thread_summary: str = "",
    allow_fallback: bool = False,
    audit_ip: str | None = None,
    audit_session: str | None = None,
) -> IngestResult:
    """Extract tasks from a parsed Gmail message and persist them."""
    existing = db.execute(
        select(Task.id).where(
            Task.created_by_id == user.id,
            Task.gmail_message_id == parsed.message_id,
        ).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return IngestResult(tasks=[], should_mark_processed=True, reason="duplicate")

    body = (parsed.body or parsed.snippet or "").strip()
    if not body:
        return IngestResult(tasks=[], should_mark_processed=True, reason="empty_body")

    extracted = orch_tasks.extract_tasks_from_email(
        sender_name=parsed.sender_name,
        sender_email=parsed.sender_email,
        subject=parsed.subject,
        body=body,
        thread_summary=thread_summary,
        allow_fallback=allow_fallback,
        module="tasks",
        operation="extract_from_email",
        user_id=user.id,
        db=db,
    )

    if not extracted:
        return IngestResult(tasks=[], should_mark_processed=True, reason="no_action")

    out: list[Task] = []
    body_excerpt = body[:6000]
    sender_display = (
        f"{parsed.sender_name} <{parsed.sender_email}>"
        if parsed.sender_email
        else parsed.from_addr
    )
    for e in extracted[:3]:
        t = Task(
            title=e.title,
            description=e.description,
            source="email",
            email_sender=sender_display,
            email_subject=parsed.subject,
            email_body=body_excerpt,
            gmail_message_id=parsed.message_id,
            gmail_thread_id=parsed.thread_id,
            priority=e.priority,
            priority_score=e.priority_score,
            status="todo",
            due_date=e.due_date,
            estimated_minutes=e.estimated_minutes,
            tags=[*e.tags, "gmail"],
            ai_confidence=e.confidence,
            ai_rationale=e.rationale,
            model_version=e.model_version,
            created_by_id=user.id,
            assigned_to_id=user.id,
        )
        db.add(t)
        db.flush()
        out.append(t)

    return IngestResult(tasks=out, should_mark_processed=True, reason="created")
