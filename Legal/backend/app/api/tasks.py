"""Task Manager — Gmail-aware task ingestion, cross-module aggregation, and
daily focus brief.

Production wires the Gmail OAuth poller into POST /tasks/ingest-email. The
scaffold accepts the parsed email payload directly so the workflow is
demonstrable without external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission
from app.database import get_db
from app.models.contract import Contract
from app.models.msa import MSATracker
from app.models.news import RegulatoryUpdate
from app.models.query import LegalBotQuery
from app.models.research import ResearchNote
from app.models.email_draft import EmailDraft
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    DailyBrief,
    TaskAggregated,
    TaskCreate,
    TaskIngestEmail,
    TaskOut,
    TaskSnooze,
    TaskUpdate,
)
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.email_ingest_service import ingest_email_as_tasks
from app.services.gmail_service import ParsedEmail


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── helpers ───────────────────────────────────────────────────────────────────


def _aggregate_for_user(db: Session, user: User) -> list[TaskAggregated]:
    """Surface platform state as virtual tasks for the current user.

    Returns suggestions the user can promote to real tasks if they want them
    tracked in this module. Permission-gated implicitly: we only query
    modules the user can reach.
    """
    out: list[TaskAggregated] = []
    role = user.role

    can_contracts = role in {"super_admin", "legal_admin", "legal_user"}
    can_msa = can_contracts
    can_research = role in {"super_admin", "legal_admin", "legal_user"}
    can_news = role in {"super_admin", "legal_admin", "legal_user"}
    can_escalations = role in {"super_admin", "legal_admin"}
    can_bot_own = role in {"super_admin", "legal_admin", "legal_user", "business_user"}

    def score(title: str, desc: str, due=None) -> tuple[str, float]:
        p, s, _ = orch_tasks.score_task_priority(
            title=title, description=desc, sender_email=None, due_date=due
        )
        return p, s

    if can_contracts:
        rows = (
            db.execute(
                select(Contract).where(Contract.status.in_(["pending_review", "under_review"]))
            )
            .scalars()
            .all()
        )
        for c in rows:
            title = f"Review contract: {c.filename}"
            desc = f"{c.contract_type} · AI risk score {c.risk_score} · {len(c.clauses)} clauses"
            p, s = score(title, desc)
            out.append(
                TaskAggregated(
                    key=f"contract:{c.id}",
                    title=title,
                    description=desc,
                    source_module="contract_review",
                    source_ref_id=c.id,
                    priority=p,
                    priority_score=s,
                    tags=["Contract"],
                )
            )

    if can_msa:
        rows = (
            db.execute(
                select(MSATracker).where(MSATracker.status.in_(["received", "under_review", "redlined"]))
            )
            .scalars()
            .all()
        )
        for m in rows:
            title = f"Decide on {m.vendor_name} {m.contract_type}"
            desc = f"Status {m.status} · risk {m.risk_score} · v{m.current_version}"
            p, s = score(title, desc)
            out.append(
                TaskAggregated(
                    key=f"msa:{m.id}",
                    title=title,
                    description=desc,
                    source_module="msa_automation",
                    source_ref_id=m.id,
                    priority=p,
                    priority_score=s,
                    tags=["Contract"],
                )
            )

    if can_escalations:
        rows = (
            db.execute(select(LegalBotQuery).where(LegalBotQuery.status == "escalated"))
            .scalars()
            .all()
        )
        for q in rows:
            title = f"Resolve escalated query: {q.question[:80]}"
            desc = f"Tier-2 LegalBot question awaiting your override."
            p, s = score(title, desc)
            out.append(
                TaskAggregated(
                    key=f"bot-escalation:{q.id}",
                    title=title,
                    description=desc,
                    source_module="legal_bot",
                    source_ref_id=q.id,
                    priority=p,
                    priority_score=s,
                    tags=["LegalBot"],
                )
            )

    if can_research:
        rows = (
            db.execute(
                select(ResearchNote)
                .where(ResearchNote.status == "draft")
                .where(ResearchNote.created_by_id == user.id)
            )
            .scalars()
            .all()
        )
        for r in rows:
            title = f"Finalise research: {r.query[:80]}"
            desc = f"Draft research note · confidence {round(r.confidence * 100)}%"
            p, s = score(title, desc)
            out.append(
                TaskAggregated(
                    key=f"research:{r.id}",
                    title=title,
                    description=desc,
                    source_module="legal_research",
                    source_ref_id=r.id,
                    priority=p,
                    priority_score=s,
                    tags=["Research"],
                )
            )

    if can_news:
        rows = (
            db.execute(select(RegulatoryUpdate).where(RegulatoryUpdate.status == "action_required"))
            .scalars()
            .all()
        )
        for n in rows:
            title = f"Act on {n.source} update: {n.title[:80]}"
            desc = n.summary[:240]
            p, s = score(title, desc)
            out.append(
                TaskAggregated(
                    key=f"news:{n.id}",
                    title=title,
                    description=desc,
                    source_module="legal_news",
                    source_ref_id=n.id,
                    priority=p,
                    priority_score=s,
                    tags=["Regulatory"],
                )
            )

    if can_bot_own:
        rows = (
            db.execute(
                select(LegalBotQuery)
                .where(LegalBotQuery.user_id == user.id)
                .where(LegalBotQuery.status == "escalated")
            )
            .scalars()
            .all()
        )
        for q in rows:
            title = f"Awaiting Legal response: {q.question[:80]}"
            desc = "Your query was escalated to the Legal team."
            p, s = score(title, desc)
            out.append(
                TaskAggregated(
                    key=f"bot-mine:{q.id}",
                    title=title,
                    description=desc,
                    source_module="legal_bot",
                    source_ref_id=q.id,
                    priority=p,
                    priority_score=s,
                    tags=["LegalBot"],
                )
            )

    # Filter out aggregations that are already crystallised as tasks
    existing_keys = _existing_aggregation_keys(db, user)
    out = [t for t in out if t.key not in existing_keys]
    out.sort(key=lambda t: t.priority_score, reverse=True)
    return out


def _existing_aggregation_keys(db: Session, user: User) -> set[str]:
    rows = (
        db.execute(
            select(Task.source_module, Task.source_ref_id).where(
                Task.created_by_id == user.id, Task.source == "module"
            )
        )
        .all()
    )
    return {f"{m}:{r}" for m, r in rows if m and r is not None}


def _streak_days(db: Session, user: User) -> int:
    """Count of consecutive days (ending today) on which user completed >=1 task."""
    rows = (
        db.execute(
            select(Task.completed_at).where(
                Task.created_by_id == user.id, Task.status == "done", Task.completed_at.is_not(None)
            )
        )
        .all()
    )
    if not rows:
        return 0
    days = {r[0].date() for r in rows}
    today = datetime.now(timezone.utc).date()
    streak = 0
    while today in days:
        streak += 1
        today = today - timedelta(days=1)
    return streak


def _filter_user_tasks(stmt, user: User):
    return stmt.where((Task.created_by_id == user.id) | (Task.assigned_to_id == user.id))


def _apply_task_scope(
    stmt,
    sources: list[str] | None = None,
    gmail_only: bool = False,
):
    """Scope tasks to Task Manager view: manual + real Gmail ingest."""
    if not sources and not gmail_only:
        return stmt
    src_list = sources or ["email", "manual"]
    conditions = []
    if "manual" in src_list:
        conditions.append(Task.source == "manual")
    if "email" in src_list:
        email_parts = [Task.source == "email"]
        if gmail_only:
            email_parts.append(Task.gmail_message_id.is_not(None))
            email_parts.append(
                or_(Task.source_module.is_(None), Task.source_module != "gmail_draft")
            )
        conditions.append(and_(*email_parts))
    if conditions:
        stmt = stmt.where(or_(*conditions))
    return stmt


# ── routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[TaskOut])
def list_tasks(
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    due: str | None = Query(default=None, description="today | overdue | week"),
    sources: list[str] | None = Query(default=None),
    gmail_only: bool = Query(default=False),
) -> list[TaskOut]:
    stmt = select(Task)
    stmt = _filter_user_tasks(stmt, user)
    stmt = _apply_task_scope(stmt, sources=sources, gmail_only=gmail_only)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    now = datetime.now(timezone.utc)
    if due == "today":
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        stmt = stmt.where(Task.due_date.is_not(None), Task.due_date <= end)
    elif due == "overdue":
        stmt = stmt.where(Task.due_date.is_not(None), Task.due_date < now, Task.status != "done")
    elif due == "week":
        end = now + timedelta(days=7)
        stmt = stmt.where(Task.due_date.is_not(None), Task.due_date <= end)
    stmt = stmt.order_by(Task.priority_score.desc(), Task.due_date.asc().nullslast(), Task.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [TaskOut.model_validate(t) for t in rows]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> TaskOut:
    if not payload.title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    label, score, rationale = orch_tasks.score_task_priority(
        title=payload.title,
        description=payload.description,
        sender_email=None,
        due_date=payload.due_date,
    )
    priority = payload.priority or label
    task = Task(
        title=payload.title,
        description=payload.description,
        source="manual",
        priority=priority,
        priority_score=score,
        status="todo",
        due_date=payload.due_date,
        estimated_minutes=payload.estimated_minutes,
        tags=payload.tags,
        ai_confidence=0.99,
        ai_rationale=rationale,
        model_version=ai.model_version,
        created_by_id=user.id,
        assigned_to_id=payload.assigned_to_id or user.id,
    )
    db.add(task)
    db.flush()
    if task.assigned_to_id and task.assigned_to_id != user.id:
        from app.services.notify_hooks import notify_task_assigned

        assignee = db.get(User, task.assigned_to_id)
        if assignee is not None:
            notify_task_assigned(
                db,
                assignee,
                user.full_name or "A colleague",
                task.title,
                task.due_date.isoformat() if task.due_date else None,
                task.id,
            )
    write_audit(
        db,
        user=user,
        action_type="task_created",
        module="tasks",
        input_summary=payload.title[:300],
        ai_output_summary=rationale,
        confidence_score=task.ai_confidence,
        model_version=task.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@router.post("/ingest-email", response_model=list[TaskOut], status_code=status.HTTP_201_CREATED)
def ingest_email(
    payload: TaskIngestEmail,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[TaskOut]:
    """AI-extract tasks from a Gmail message body."""
    import uuid

    parsed = ParsedEmail(
        message_id=f"manual-{uuid.uuid4().hex}",
        thread_id="manual",
        subject=payload.subject,
        from_addr=f"{payload.sender_name} <{payload.sender_email}>",
        to_addr="",
        body=payload.body,
        snippet=payload.body[:120],
        date=None,
        sender_name=payload.sender_name,
        sender_email=str(payload.sender_email),
    )
    result = ingest_email_as_tasks(
        db,
        user,
        parsed,
        allow_fallback=True,
        audit_ip=client_ip(request),
        audit_session=session_id(request),
    )
    write_audit(
        db,
        user=user,
        action_type="task_ingest_email",
        module="tasks",
        input_summary=payload.subject[:300],
        ai_output_summary=f"created={len(result.tasks)}",
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    for t in result.tasks:
        db.refresh(t)
    return [TaskOut.model_validate(t) for t in result.tasks]


@router.post("/promote", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def promote_aggregated(
    request: Request,
    key: str = Query(..., description="Aggregation key, e.g. 'contract:42'"),
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> TaskOut:
    suggestions = _aggregate_for_user(db, user)
    match = next((s for s in suggestions if s.key == key), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aggregation not found or already promoted")
    task = Task(
        title=match.title,
        description=match.description,
        source="module",
        source_module=match.source_module,
        source_ref_id=match.source_ref_id,
        priority=match.priority,
        priority_score=match.priority_score,
        status="todo",
        due_date=match.due_date,
        tags=match.tags,
        ai_confidence=0.85,
        ai_rationale=f"Auto-derived from {match.source_module}",
        model_version=orch_tasks.model_version(),
        created_by_id=user.id,
        assigned_to_id=user.id,
    )
    db.add(task)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="task_promoted",
        module="tasks",
        input_summary=match.title[:300],
        ai_output_summary=f"source={match.source_module} ref={match.source_ref_id}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@router.get("/aggregate", response_model=list[TaskAggregated])
def aggregated(
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[TaskAggregated]:
    return _aggregate_for_user(db, user)


@router.get("/daily-brief", response_model=DailyBrief)
def daily_brief(
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> DailyBrief:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Active (non-done) tasks for the user — Task Manager scope
    active_stmt = _filter_user_tasks(select(Task), user).where(Task.status != "done")
    active_stmt = _apply_task_scope(
        active_stmt, sources=["email", "manual"], gmail_only=True
    )
    active = db.execute(active_stmt).scalars().all()

    by_priority = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    overdue = 0
    for t in active:
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        if t.due_date and t.due_date < now:
            overdue += 1

    completed_today = (
        db.execute(
            _apply_task_scope(
                _filter_user_tasks(select(Task), user)
                .where(Task.status == "done")
                .where(Task.completed_at.is_not(None))
                .where(Task.completed_at >= today_start),
                sources=["email", "manual"],
                gmail_only=True,
            )
        )
        .scalars()
        .all()
    )

    top_active = sorted(active, key=lambda t: t.priority_score, reverse=True)[:5]
    streak = _streak_days(db, user)

    # AI-style summary string (deterministic, but humanised)
    parts: list[str] = []
    if by_priority["P0"] > 0:
        parts.append(f"{by_priority['P0']} P0 item{'s' if by_priority['P0'] != 1 else ''} demanding immediate attention")
    if by_priority["P1"] > 0:
        parts.append(f"{by_priority['P1']} P1 follow-up{'s' if by_priority['P1'] != 1 else ''}")
    if overdue > 0:
        parts.append(f"{overdue} overdue")
    if not parts:
        parts.append("a clean board")

    headline = f"You have {sum(by_priority.values())} active task{'s' if sum(by_priority.values()) != 1 else ''} — " + ", ".join(parts) + "."
    if top_active:
        headline += f" Start with: \"{top_active[0].title[:90]}\"."
    if streak > 0:
        headline += f" {streak}-day streak in motion — keep it going."
    if len(completed_today) > 0:
        headline += f" {len(completed_today)} done today already."

    aggregated_suggestions = _aggregate_for_user(db, user)

    day_ago = now - timedelta(hours=24)
    new_gmail_tasks = (
        db.execute(
            _filter_user_tasks(select(Task), user)
            .where(Task.source == "email")
            .where(Task.gmail_message_id.is_not(None))
            .where(Task.created_at >= day_ago)
        )
        .scalars()
        .all()
    )
    pending_drafts = (
        db.execute(
            select(EmailDraft).where(
                EmailDraft.user_id == user.id,
                EmailDraft.status.in_(("draft", "user_edited", "approved")),
            )
        )
        .scalars()
        .all()
    )

    if new_gmail_tasks:
        headline += f" {len(new_gmail_tasks)} new Gmail task{'s' if len(new_gmail_tasks) != 1 else ''} in the last 24h."
    if pending_drafts:
        headline += f" {len(pending_drafts)} email draft{'s' if len(pending_drafts) != 1 else ''} awaiting send."

    return DailyBrief(
        summary=headline,
        counts=by_priority,
        streak_days=streak,
        completed_today=len(completed_today),
        overdue=overdue,
        new_gmail_tasks_count=len(new_gmail_tasks),
        pending_email_drafts=len(pending_drafts),
        top_priorities=[TaskOut.model_validate(t) for t in top_active],
        aggregated_suggestions=aggregated_suggestions[:6],
    )


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.created_by_id != user.id and task.assigned_to_id != user.id:
        # Legal Admins and Super Admins can edit anyone's tasks via the
        # assignment flow; otherwise it's restricted.
        if user.role not in ("super_admin", "legal_admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit this task")
    data = payload.model_dump(exclude_unset=True)
    prev_assignee_id = task.assigned_to_id
    decision: str | None = None
    for field, value in data.items():
        setattr(task, field, value)
        if field == "status":
            decision = value
            if value == "done":
                task.completed_at = datetime.now(timezone.utc)
            elif value != "done":
                task.completed_at = None

    # Re-score priority if fields changed
    if any(k in data for k in ("title", "description", "due_date")):
        label, score, rationale = orch_tasks.score_task_priority(
            title=task.title,
            description=task.description,
            sender_email=None,
            due_date=task.due_date,
        )
        if "priority" not in data:
            task.priority = label
        task.priority_score = score
        task.ai_rationale = rationale

    # Notify a newly-assigned user (reassignment), skipping self-assignment.
    if (
        task.assigned_to_id
        and task.assigned_to_id != prev_assignee_id
        and task.assigned_to_id != user.id
    ):
        from app.services.notify_hooks import notify_task_assigned

        assignee = db.get(User, task.assigned_to_id)
        if assignee is not None:
            notify_task_assigned(
                db,
                assignee,
                user.full_name or "A colleague",
                task.title,
                task.due_date.isoformat() if task.due_date else None,
                task.id,
            )

    write_audit(
        db,
        user=user,
        action_type="task_updated",
        module="tasks",
        input_summary=payload.model_dump_json(exclude_unset=True)[:500],
        human_decision=decision,
        model_version=task.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@router.post("/{task_id}/snooze", response_model=TaskOut)
def snooze_task(
    task_id: int,
    payload: TaskSnooze,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None or (
        task.created_by_id != user.id
        and task.assigned_to_id != user.id
        and user.role not in ("super_admin", "legal_admin")
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task.snoozed_until = payload.snoozed_until
    task.status = "snoozed"
    write_audit(
        db,
        user=user,
        action_type="task_snoozed",
        module="tasks",
        input_summary=f"until={payload.snoozed_until.isoformat()}",
        human_decision="snoozed",
        model_version=task.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=task.id,
    )
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.created_by_id != user.id and user.role not in ("super_admin", "legal_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete this task")
    deleted_id = task.id
    write_audit(
        db,
        user=user,
        action_type="task_deleted",
        module="tasks",
        input_summary=task.title[:300],
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=deleted_id,
    )
    db.delete(task)
    db.commit()
    return {"deleted": deleted_id}
