"""Gmail → MSA vendor docx auto-ingest from watched and linked threads."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.gmail_credential import GmailCredential
from app.models.gmail_settings import GmailSettings
from app.models.msa import MSAEmail, MSATracker
from app.models.msa_share import MSAShare
from app.models.msa_version import MSADocumentVersion
from app.models.user import User
from app.orchestrator import tasks as orch_tasks
from app.services.gmail_service import (
    ParsedEmail,
    _parse_from_header,
    first_docx_attachment,
    get_gmail_service,
    parse_gmail_message,
)
from app.services.msa_access import ACCESS_EDIT, ACCESS_OWNER, access_level_for, is_msa_owner
from app.services.msa_version_service import ingest_file_version, risk_score_from_suggestions
from app.services.review_workspace_service import (
    format_regulatory_context,
    load_playbook_context,
    normalize_findings,
)
from app.services.suggestion_service import filter_actionable_suggestions

logger = logging.getLogger(__name__)

MAX_MSA_THREADS_PER_POLL = 10
MAX_MSA_MESSAGES_PER_THREAD = 5


def _get_or_create_settings(db: Session, user_id: int) -> GmailSettings:
    row = db.execute(
        select(GmailSettings).where(GmailSettings.user_id == user_id)
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = GmailSettings(user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@dataclass
class _ThreadTarget:
    thread_id: str
    tracker_id: int | None = None
    vendor_email: str | None = None


def _message_already_ingested(db: Session, message_id: str) -> bool:
    version_hit = db.execute(
        select(MSADocumentVersion.id).where(MSADocumentVersion.gmail_message_id == message_id).limit(1)
    ).scalar_one_or_none()
    if version_hit is not None:
        return True
    email_hit = db.execute(
        select(MSAEmail.id).where(MSAEmail.gmail_message_id == message_id).limit(1)
    ).scalar_one_or_none()
    return email_hit is not None


def _parse_message_date(parsed: ParsedEmail) -> datetime | None:
    if not parsed.date:
        return None
    try:
        dt = parsedate_to_datetime(parsed.date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _within_lookback(parsed: ParsedEmail, lookback_days: int) -> bool:
    dt = _parse_message_date(parsed)
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return dt >= cutoff


def _is_inbound(sender_email: str, account_email: str) -> bool:
    if not sender_email or not account_email:
        return True
    return sender_email.strip().lower() != account_email.strip().lower()


def _accessible_trackers_with_threads(db: Session, user: User) -> list[MSATracker]:
    if is_msa_owner(user):
        rows = db.execute(
            select(MSATracker).where(
                MSATracker.gmail_thread_id.isnot(None),
                MSATracker.gmail_auto_ingest.is_(True),
            )
        ).scalars().all()
        return list(rows)
    shared_ids = (
        db.execute(
            select(MSAShare.tracker_id).where(
                MSAShare.user_id == user.id,
                MSAShare.access_level == ACCESS_EDIT,
            )
        )
        .scalars()
        .all()
    )
    if not shared_ids:
        return []
    rows = db.execute(
        select(MSATracker).where(
            MSATracker.id.in_(shared_ids),
            MSATracker.gmail_thread_id.isnot(None),
            MSATracker.gmail_auto_ingest.is_(True),
        )
    ).scalars().all()
    return list(rows)


def _collect_thread_targets(db: Session, user: User, gmail_settings: GmailSettings) -> list[_ThreadTarget]:
    by_thread: dict[str, _ThreadTarget] = {}
    for tracker in _accessible_trackers_with_threads(db, user):
        tid = tracker.gmail_thread_id
        if not tid:
            continue
        by_thread[tid] = _ThreadTarget(
            thread_id=tid,
            tracker_id=tracker.id,
            vendor_email=tracker.vendor_email,
        )
    for watch in gmail_settings.msa_watched_threads or []:
        if not isinstance(watch, dict):
            continue
        tid = watch.get("thread_id")
        if not tid:
            continue
        existing = by_thread.get(tid)
        tracker_id = watch.get("tracker_id")
        if existing and existing.tracker_id:
            continue
        by_thread[tid] = _ThreadTarget(
            thread_id=tid,
            tracker_id=tracker_id,
            vendor_email=watch.get("vendor_email"),
        )
    return list(by_thread.values())


def _update_watch_tracker_id(
    db: Session,
    user: User,
    thread_id: str,
    tracker_id: int,
) -> None:
    row = _get_or_create_settings(db, user.id)
    watches = list(row.msa_watched_threads or [])
    changed = False
    for w in watches:
        if isinstance(w, dict) and w.get("thread_id") == thread_id:
            w["tracker_id"] = tracker_id
            changed = True
    if changed:
        row.msa_watched_threads = watches
        db.flush()


def _run_initial_review(
    db: Session,
    tracker: MSATracker,
    user: User,
    base_text: str,
) -> None:
    ctx = load_playbook_context(db, tracker.contract_type)
    reg_block = format_regulatory_context(ctx.regulatory_snippets)
    review_text = base_text
    if reg_block:
        review_text = f"{reg_block}\n\n---\n\n{base_text}"
    result = orch_tasks.review_contract(
        review_text,
        ctx.clauses,
        contract_type=tracker.contract_type,
        module="msa_automation",
        operation="review_contract",
        user_id=user.id,
        db=db,
    )
    suggestions = filter_actionable_suggestions(
        normalize_findings(result.clauses, ctx.clauses, ctx.clause_bank)
    )
    tracker.ai_suggestions = suggestions
    tracker.risk_score = risk_score_from_suggestions(suggestions) if suggestions else result.risk_score
    tracker.status = "under_review"


def _auto_create_tracker_from_vendor(
    db: Session,
    user: User,
    parsed: ParsedEmail,
    data: bytes,
    fname: str,
    mime: str,
    message_id: str,
    thread_id: str,
    account_email: str,
) -> MSATracker:
    vendor_name, vendor_email = _parse_from_header(parsed.from_addr)
    if not vendor_email:
        vendor_email = parsed.sender_email or "vendor@unknown"
    if not vendor_name:
        vendor_name = vendor_email.split("@")[0]

    tracker = MSATracker(
        vendor_name=vendor_name[:256],
        vendor_email=vendor_email[:256],
        contract_type="MSA",
        status="under_review",
        current_version=0,
        gmail_thread_id=thread_id,
        gmail_auto_ingest=True,
        assigned_to_id=user.id,
    )
    db.add(tracker)
    db.flush()

    version, _ = ingest_file_version(
        db,
        tracker,
        data,
        fname,
        mime,
        source="legal_base",
        user=user,
        gmail_message_id=message_id,
    )
    _run_initial_review(db, tracker, user, version.extracted_text or "")

    db.add(
        MSAEmail(
            tracker_id=tracker.id,
            version_id=version.id,
            direction="in",
            from_addr=parsed.from_addr,
            to_addr=account_email,
            subject=parsed.subject,
            body=parsed.body or "(attachment)",
            attachment_name=fname,
            gmail_message_id=message_id,
        )
    )
    _update_watch_tracker_id(db, user, thread_id, tracker.id)
    return tracker


def _ingest_vendor_return(
    db: Session,
    tracker: MSATracker,
    user: User,
    parsed: ParsedEmail,
    data: bytes,
    fname: str,
    mime: str,
    message_id: str,
    account_email: str,
) -> MSADocumentVersion:
    version, _ = ingest_file_version(
        db,
        tracker,
        data,
        fname,
        mime,
        source="vendor_return",
        user=user,
        gmail_message_id=message_id,
    )
    db.add(
        MSAEmail(
            tracker_id=tracker.id,
            version_id=version.id,
            direction="in",
            from_addr=parsed.from_addr,
            to_addr=account_email,
            subject=parsed.subject,
            body=parsed.body or "(attachment)",
            attachment_name=fname,
            gmail_message_id=message_id,
        )
    )
    return version


def poll_msa_vendor_threads(db: Session, user: User) -> dict:
    """Scan linked/watched Gmail threads and auto-ingest vendor docx attachments."""
    summary: dict = {
        "ingested": [],
        "auto_created": [],
        "skipped": 0,
        "errors": [],
    }
    svc = get_gmail_service()
    if not settings.gmail_enabled or not svc.is_configured():
        return summary

    cred = db.execute(
        select(GmailCredential).where(GmailCredential.user_id == user.id)
    ).scalar_one_or_none()
    if cred is None:
        return summary

    gmail_settings = _get_or_create_settings(db, user.id)
    lookback = max(1, min(gmail_settings.poll_lookback_days or 7, 30))
    targets = _collect_thread_targets(db, user, gmail_settings)[:MAX_MSA_THREADS_PER_POLL]
    if not targets:
        return summary

    token = svc._refresh_if_needed(db, cred)
    ingested_count = 0

    for target in targets:
        try:
            raw_thread = svc._api(token, f"/threads/{target.thread_id}?format=full")
            messages = [parse_gmail_message(m) for m in raw_thread.get("messages", [])]
            messages = [m for m in messages if _within_lookback(m, lookback)]
            messages = messages[-MAX_MSA_MESSAGES_PER_THREAD:]

            for parsed in messages:
                if _message_already_ingested(db, parsed.message_id):
                    summary["skipped"] += 1
                    continue
                if not _is_inbound(parsed.sender_email, cred.email):
                    summary["skipped"] += 1
                    continue

                raw_msg = next(
                    (m for m in raw_thread.get("messages", []) if m.get("id") == parsed.message_id),
                    None,
                )
                if raw_msg is None:
                    continue
                attachment = first_docx_attachment(
                    parsed.message_id,
                    raw_msg.get("payload", {}),
                    token,
                    svc,
                )
                if attachment is None:
                    continue

                data, fname, mime = attachment
                tracker: MSATracker | None = None
                if target.tracker_id:
                    tracker = db.get(MSATracker, target.tracker_id)
                    if tracker is None:
                        continue
                    level = access_level_for(user, tracker.id, db)
                    if level not in (ACCESS_OWNER, ACCESS_EDIT):
                        continue

                if tracker is None:
                    tracker = _auto_create_tracker_from_vendor(
                        db,
                        user,
                        parsed,
                        data,
                        fname,
                        mime,
                        parsed.message_id,
                        target.thread_id,
                        cred.email,
                    )
                    db.commit()
                    summary["auto_created"].append(
                        {
                            "message_id": parsed.message_id,
                            "tracker_id": tracker.id,
                            "thread_id": target.thread_id,
                            "filename": fname,
                        }
                    )
                    from app.services.notify_hooks import notify_msa_vendor_ingested

                    notify_msa_vendor_ingested(db, user, tracker.vendor_name or "a vendor", tracker.id)
                    db.commit()
                else:
                    if not tracker.gmail_thread_id:
                        tracker.gmail_thread_id = target.thread_id
                    version = _ingest_vendor_return(
                        db,
                        tracker,
                        user,
                        parsed,
                        data,
                        fname,
                        mime,
                        parsed.message_id,
                        cred.email,
                    )
                    db.commit()
                    from app.services.notify_hooks import notify_msa_vendor_ingested

                    notify_msa_vendor_ingested(db, user, tracker.vendor_name or "a vendor", tracker.id)
                    db.commit()
                    summary["ingested"].append(
                        {
                            "message_id": parsed.message_id,
                            "tracker_id": tracker.id,
                            "version_id": version.id,
                            "filename": fname,
                        }
                    )
                ingested_count += 1
        except Exception as exc:
            db.rollback()
            logger.exception("MSA Gmail poll failed thread=%s user=%s", target.thread_id, user.id)
            summary["errors"].append(f"thread:{target.thread_id}:{exc}")

    return summary


def add_msa_watch(
    db: Session,
    user: User,
    *,
    thread_id: str,
    tracker_id: int | None = None,
    subject: str | None = None,
    vendor_email: str | None = None,
) -> list[dict]:
    row = _get_or_create_settings(db, user.id)
    watches = list(row.msa_watched_threads or [])
    entry = {
        "thread_id": thread_id,
        "tracker_id": tracker_id,
        "subject": subject,
        "vendor_email": vendor_email,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    watches = [w for w in watches if not (isinstance(w, dict) and w.get("thread_id") == thread_id)]
    watches.append(entry)
    row.msa_watched_threads = watches
    db.commit()
    return watches


def remove_msa_watch(db: Session, user: User, thread_id: str) -> list[dict]:
    row = _get_or_create_settings(db, user.id)
    watches = [
        w
        for w in (row.msa_watched_threads or [])
        if not (isinstance(w, dict) and w.get("thread_id") == thread_id)
    ]
    row.msa_watched_threads = watches
    db.commit()
    return watches


def list_msa_watches(db: Session, user: User) -> list[dict]:
    row = _get_or_create_settings(db, user.id)
    return list(row.msa_watched_threads or [])
