"""Gmail OAuth, settings, read APIs, drafts, and polling."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_permission, session_id
from app.config import settings
from app.core.rbac import Permission
from app.database import get_db
from app.models.email_draft import EmailDraft
from app.models.gmail_credential import GmailCredential
from app.models.gmail_settings import GmailSettings
from app.models.user import User
from app.schemas.gmail import (
    EmailDraftApprove,
    EmailDraftCreate,
    EmailDraftOut,
    EmailDraftUpdate,
    GmailLabelOut,
    GmailMessageListOut,
    GmailMessageOut,
    GmailMessageSummary,
    GmailSettingsOut,
    GmailSettingsUpdate,
    GmailThreadOut,
    WatchedSenderIn,
    WatchedThreadIn,
)
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.email_ingest_service import ingest_email_as_tasks
from app.services.gmail_poll_service import get_or_create_settings, poll_user_gmail
from app.services.gmail_service import _label_query_part, get_gmail_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gmail", tags=["gmail"])

_GMAIL_PERMS = (Permission.MSA_AUTOMATION, Permission.TASK_MANAGEMENT)


def _gmail_status_payload(db: Session, user: User) -> dict:
    svc = get_gmail_service()
    cred = db.execute(
        select(GmailCredential).where(GmailCredential.user_id == user.id)
    ).scalar_one_or_none()
    return {
        "configured": svc.is_configured(),
        "enabled": settings.gmail_enabled,
        "connected": cred is not None,
        "email": cred.email if cred else None,
    }


def _settings_out(db: Session, user: User) -> GmailSettingsOut:
    row = get_or_create_settings(db, user.id)
    cred = db.execute(
        select(GmailCredential).where(GmailCredential.user_id == user.id)
    ).scalar_one_or_none()
    return GmailSettingsOut(
        poll_enabled=row.poll_enabled,
        poll_labels=row.poll_labels or [],
        auto_task_ingest=row.auto_task_ingest,
        poll_lookback_days=row.poll_lookback_days or 7,
        watched_threads=row.watched_threads or [],
        watched_senders=row.watched_senders or [],
        msa_watched_threads=row.msa_watched_threads or [],
        default_context_module=row.default_context_module,
        last_poll_at=row.last_poll_at,
        connected=cred is not None,
        email=cred.email if cred else None,
    )


@router.get("/status")
def gmail_status(
    user: User = Depends(require_permission(*_GMAIL_PERMS)),
    db: Session = Depends(get_db),
) -> dict:
    return _gmail_status_payload(db, user)


@router.get("/settings", response_model=GmailSettingsOut)
def get_settings(
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailSettingsOut:
    return _settings_out(db, user)


@router.patch("/settings", response_model=GmailSettingsOut)
def update_settings(
    payload: GmailSettingsUpdate,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailSettingsOut:
    row = get_or_create_settings(db, user.id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _settings_out(db, user)


@router.post("/watches/threads", response_model=GmailSettingsOut)
def watch_thread(
    payload: WatchedThreadIn,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailSettingsOut:
    row = get_or_create_settings(db, user.id)
    watches = list(row.watched_threads or [])
    if not any(w.get("thread_id") == payload.thread_id for w in watches if isinstance(w, dict)):
        watches.append(
            {
                "thread_id": payload.thread_id,
                "subject": payload.subject,
                "from_addr": payload.from_addr,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        row.watched_threads = watches
        db.commit()
    return _settings_out(db, user)


@router.delete("/watches/threads/{thread_id}", response_model=GmailSettingsOut)
def unwatch_thread(
    thread_id: str,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailSettingsOut:
    row = get_or_create_settings(db, user.id)
    row.watched_threads = [
        w for w in (row.watched_threads or []) if isinstance(w, dict) and w.get("thread_id") != thread_id
    ]
    db.commit()
    return _settings_out(db, user)


@router.post("/watches/senders", response_model=GmailSettingsOut)
def watch_sender(
    payload: WatchedSenderIn,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailSettingsOut:
    row = get_or_create_settings(db, user.id)
    email = payload.email.strip().lower()
    senders = [s.lower() for s in (row.watched_senders or [])]
    if email and email not in senders:
        senders.append(email)
        row.watched_senders = senders
        db.commit()
    return _settings_out(db, user)


@router.delete("/watches/senders/{email}", response_model=GmailSettingsOut)
def unwatch_sender(
    email: str,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailSettingsOut:
    row = get_or_create_settings(db, user.id)
    target = email.strip().lower()
    row.watched_senders = [s for s in (row.watched_senders or []) if s.lower() != target]
    db.commit()
    return _settings_out(db, user)


@router.get("/oauth/start")
def oauth_start(
    return_to: str = Query("tasks"),
    user: User = Depends(require_permission(*_GMAIL_PERMS)),
) -> dict:
    svc = get_gmail_service()
    if not svc.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail OAuth not configured (set GMAIL_CLIENT_ID/SECRET)",
        )
    safe_return = return_to if return_to in ("tasks", "msa-automation", "settings") else "tasks"
    state = f"{user.id}:{secrets.token_urlsafe(16)}:{safe_return}"
    return {"authorization_url": svc.authorization_url(state), "state": state}


@router.get("/oauth/callback")
def oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    import urllib.error

    svc = get_gmail_service()
    parts = state.split(":", 2)
    try:
        user_id = int(parts[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state") from None
    return_to = parts[2] if len(parts) > 2 else "tasks"
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    path = f"/{return_to}" if not return_to.startswith("/") else return_to

    try:
        tokens = svc.exchange_code(code)
        gmail_email = svc.fetch_connected_email(tokens["access_token"])
        svc.save_credentials(db, user, tokens, gmail_email or user.email)
        get_or_create_settings(db, user.id)
        return RedirectResponse(url=f"{frontend}{path}?gmail=connected")
    except urllib.error.HTTPError as exc:
        logger.exception("Gmail OAuth callback failed for user_id=%s", user_id)
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        reason = "token_exchange_failed" if exc.code == 400 else "profile_fetch_failed"
        if "invalid_grant" in body:
            reason = "code_already_used"
        return RedirectResponse(url=f"{frontend}{path}?gmail=error&reason={reason}")
    except Exception:
        logger.exception("Gmail OAuth callback failed for user_id=%s", user_id)
        return RedirectResponse(url=f"{frontend}{path}?gmail=error&reason=unknown")


@router.get("/labels", response_model=list[GmailLabelOut])
def list_labels(
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[GmailLabelOut]:
    svc = get_gmail_service()
    try:
        labels = svc.list_labels(db, user)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [GmailLabelOut(id=l["id"], name=l["name"], type=l.get("type", "user")) for l in labels]


@router.get("/messages", response_model=GmailMessageListOut)
def list_messages(
    subject: str | None = None,
    from_addr: str | None = None,
    label: str | None = None,
    q: str | None = None,
    newer_than_days: int | None = Query(None, ge=1, le=365),
    max_results: int = Query(20, ge=1, le=50),
    page_token: str | None = None,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailMessageListOut:
    svc = get_gmail_service()
    try:
        parts: list[str] = []
        if q:
            parts.append(q)
        if subject:
            parts.append(f'subject:"{subject}"')
        if from_addr:
            parts.append(f"from:{from_addr}")
        if label:
            parts.append(_label_query_part(label))
        if newer_than_days is not None:
            parts.append(f"newer_than:{newer_than_days}d")
        query = " ".join(parts)
        rows, next_token = svc.list_messages(
            db, user, query=query, max_results=max_results, page_token=page_token
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GmailMessageListOut(
        messages=[GmailMessageSummary(**r) for r in rows],
        next_page_token=next_token,
    )


@router.get("/messages/{message_id}", response_model=GmailMessageOut)
def get_message(
    message_id: str,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> GmailMessageOut:
    svc = get_gmail_service()
    try:
        parsed = svc.get_message(db, user, message_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GmailMessageOut(
        id=parsed.message_id,
        thread_id=parsed.thread_id,
        subject=parsed.subject,
        from_addr=parsed.from_addr,
        to_addr=parsed.to_addr,
        body=parsed.body,
        date=parsed.date,
    )


@router.get("/threads/{thread_id}", response_model=GmailThreadOut)
def get_thread(
    thread_id: str,
    user: User = Depends(require_permission(*_GMAIL_PERMS)),
    db: Session = Depends(get_db),
) -> GmailThreadOut:
    svc = get_gmail_service()
    try:
        messages = svc.get_thread(db, user, thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GmailThreadOut(
        id=thread_id,
        messages=[
            GmailMessageOut(
                id=m.message_id,
                thread_id=m.thread_id,
                subject=m.subject,
                from_addr=m.from_addr,
                to_addr=m.to_addr,
                body=m.body,
                date=m.date,
            )
            for m in messages
        ],
    )


@router.post("/poll")
def poll_gmail(
    force_ingest: bool = Query(False),
    msa_only: bool = Query(False),
    user: User = Depends(require_permission(*_GMAIL_PERMS)),
    db: Session = Depends(get_db),
) -> dict:
    summary = poll_user_gmail(db, user, force_ingest=force_ingest, msa_only=msa_only)
    return summary


@router.post("/messages/{message_id}/ingest-tasks")
def ingest_message_tasks(
    message_id: str,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> dict:
    svc = get_gmail_service()
    try:
        parsed = svc.get_message(db, user, message_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = ingest_email_as_tasks(
        db,
        user,
        parsed,
        allow_fallback=True,
        audit_ip=client_ip(request),
        audit_session=session_id(request),
    )
    if result.should_mark_processed:
        settings_row = get_or_create_settings(db, user.id)
        from app.services.gmail_service import mark_message_processed

        settings_row.processed_message_ids = mark_message_processed(
            settings_row.processed_message_ids or [],
            message_id,
        )
    if result.tasks:
        write_audit(
            db,
            user=user,
            action_type="gmail_ingest_tasks",
            module="tasks",
            input_summary=parsed.subject[:300],
            ai_output_summary=f"created={len(result.tasks)}",
            ip_address=client_ip(request),
            session_id=session_id(request),
        )
        db.commit()
    return {
        "count": len(result.tasks),
        "task_ids": [t.id for t in result.tasks],
        "reason": result.reason,
    }


# ── Email drafts (AI reply workflow) ─────────────────────────────────────────


@router.get("/drafts", response_model=list[EmailDraftOut])
def list_drafts(
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> list[EmailDraftOut]:
    q = select(EmailDraft).where(EmailDraft.user_id == user.id).order_by(EmailDraft.id.desc())
    if status_filter:
        q = q.where(EmailDraft.status == status_filter)
    rows = db.execute(q).scalars().all()
    return [EmailDraftOut.model_validate(r) for r in rows]


@router.get("/drafts/{draft_id}", response_model=EmailDraftOut)
def get_draft(
    draft_id: int,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    draft = db.get(EmailDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return EmailDraftOut.model_validate(draft)


@router.post("/drafts", response_model=EmailDraftOut, status_code=status.HTTP_201_CREATED)
def create_draft(
    payload: EmailDraftCreate,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    svc = get_gmail_service()
    try:
        parsed = svc.get_message(db, user, payload.gmail_message_id)
        thread_messages = svc.get_thread(db, user, payload.gmail_thread_id)
        ctx = svc.thread_context_for_ai(thread_messages, payload.gmail_message_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    result = orch_tasks.generate_email_reply(
        latest_body=ctx["latest_body"],
        original_subject=parsed.subject,
        from_addr=parsed.from_addr,
        prior_summary=ctx.get("prior_summary", ""),
        user_feedback=payload.user_feedback,
        module="gmail",
        operation="generate_reply",
        user_id=user.id,
        db=db,
    )

    draft = EmailDraft(
        user_id=user.id,
        gmail_thread_id=payload.gmail_thread_id,
        gmail_message_id=payload.gmail_message_id,
        original_subject=parsed.subject,
        original_body=parsed.body[:12000],
        from_addr=parsed.from_addr,
        to_addr=parsed.sender_email or parsed.from_addr,
        draft_subject=result.subject,
        draft_body=result.body,
        status="draft",
        user_feedback=payload.user_feedback,
        model_version=result.model_version,
    )
    db.add(draft)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="email_draft_created",
        module="gmail",
        input_summary=parsed.subject[:300],
        ai_output_summary=result.body[:300],
        confidence_score=result.confidence,
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=draft.id,
    )
    db.commit()
    db.refresh(draft)
    return EmailDraftOut.model_validate(draft)


@router.patch("/drafts/{draft_id}", response_model=EmailDraftOut)
def update_draft(
    draft_id: int,
    payload: EmailDraftUpdate,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    draft = db.get(EmailDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(draft, field, value)
    if "draft_body" in data or "draft_subject" in data:
        # Any content edit invalidates a prior approval — user must re-approve before send.
        if draft.status in ("draft", "approved"):
            draft.status = "user_edited"
    db.commit()
    db.refresh(draft)
    return EmailDraftOut.model_validate(draft)


@router.post("/drafts/{draft_id}/regenerate", response_model=EmailDraftOut)
def regenerate_draft(
    draft_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    draft = db.get(EmailDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    svc = get_gmail_service()
    try:
        thread_messages = svc.get_thread(db, user, draft.gmail_thread_id)
        ctx = svc.thread_context_for_ai(thread_messages, draft.gmail_message_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = orch_tasks.generate_email_reply(
        latest_body=ctx["latest_body"],
        original_subject=draft.original_subject,
        from_addr=draft.from_addr,
        prior_summary=ctx.get("prior_summary", ""),
        user_feedback=draft.user_feedback,
        module="gmail",
        operation="regenerate_reply",
        user_id=user.id,
        db=db,
    )
    draft.draft_subject = result.subject
    draft.draft_body = result.body
    draft.status = "draft"
    draft.model_version = result.model_version
    write_audit(
        db,
        user=user,
        action_type="email_draft_regenerated",
        module="gmail",
        input_summary=draft.original_subject[:300],
        ai_output_summary=result.body[:300],
        confidence_score=result.confidence,
        model_version=result.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=draft.id,
    )
    db.commit()
    db.refresh(draft)
    return EmailDraftOut.model_validate(draft)


@router.post("/drafts/{draft_id}/approve", response_model=EmailDraftOut)
def approve_draft(
    draft_id: int,
    payload: EmailDraftApprove,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    draft = db.get(EmailDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    draft.status = "approved"
    if payload.remind_in_hours > 0:
        draft.remind_at = datetime.now(timezone.utc) + timedelta(hours=payload.remind_in_hours)
    else:
        draft.remind_at = None
    db.commit()
    db.refresh(draft)
    return EmailDraftOut.model_validate(draft)


@router.post("/drafts/{draft_id}/send", response_model=EmailDraftOut)
def send_draft(
    draft_id: int,
    request: Request,
    user: User = Depends(require_permission(Permission.SEND_EMAIL)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    draft = db.get(EmailDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    if draft.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draft must be approved before sending",
        )
    svc = get_gmail_service()
    to_addr = draft.to_addr or draft.from_addr
    try:
        svc.send_message(
            db,
            user,
            to_addr=to_addr,
            subject=draft.draft_subject,
            body=draft.draft_body,
            thread_id=draft.gmail_thread_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    draft.status = "sent"
    draft.sent_at = datetime.now(timezone.utc)
    draft.remind_at = None
    write_audit(
        db,
        user=user,
        action_type="email_draft_sent",
        module="gmail",
        input_summary=draft.draft_subject[:300],
        ai_output_summary=draft.draft_body[:300],
        human_decision="send",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=draft.id,
    )
    db.commit()
    db.refresh(draft)
    return EmailDraftOut.model_validate(draft)


@router.post("/drafts/{draft_id}/dismiss", response_model=EmailDraftOut)
def dismiss_draft(
    draft_id: int,
    user: User = Depends(require_permission(Permission.TASK_MANAGEMENT)),
    db: Session = Depends(get_db),
) -> EmailDraftOut:
    draft = db.get(EmailDraft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    draft.status = "dismissed"
    draft.remind_at = None
    db.commit()
    db.refresh(draft)
    return EmailDraftOut.model_validate(draft)
