"""Orchestrate Gmail polling across Task Manager and MSA modules."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_draft import EmailDraft
from app.models.gmail_credential import GmailCredential
from app.models.gmail_settings import GmailSettings
from app.models.task import Task
from app.models.user import User
from app.orchestrator import tasks as orch_tasks
from app.services.audit_service import write_audit
from app.services.email_ingest_service import ingest_email_as_tasks
from app.services.gmail_service import ParsedEmail, get_gmail_service, mark_message_processed

# Task priorities that trigger an auto-generated reply draft for user review.
AUTODRAFT_PRIORITIES = ("P0", "P1")

logger = logging.getLogger(__name__)

# Cap AI ingest per poll so manual Poll stays responsive (full inbox still counted as scanned).
MAX_INGEST_PER_POLL = 25


def get_or_create_settings(db: Session, user_id: int) -> GmailSettings:
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


def _collect_poll_messages(
    db: Session,
    user: User,
    settings: GmailSettings,
    processed_set: set[str],
    *,
    force_ingest: bool = False,
) -> tuple[list[ParsedEmail], list[str]]:
    svc = get_gmail_service()
    lookback = max(1, min(settings.poll_lookback_days or 7, 30))
    by_id: dict[str, ParsedEmail] = {}
    sources: list[str] = []

    labels = list(settings.poll_labels or [])
    watched_senders = list(settings.watched_senders or [])
    watched_threads = list(settings.watched_threads or [])

    # Task ingestion is watch-only: both auto poll and manual "Poll" only look at
    # explicitly configured labels / watched senders / watched threads. Arbitrary
    # inbox mail never becomes a task — use the per-message "Ingest tasks" action
    # for one-off emails outside a watch.
    for label in labels:
        sources.append(f"label:{label}")
        try:
            for parsed in svc.poll_label_messages(
                db,
                user,
                label,
                newer_than_days=lookback,
                processed_ids=processed_set,
                exclude_processed=False,
            ):
                by_id[parsed.message_id] = parsed
        except Exception as exc:
            logger.exception("Gmail label poll failed user=%s label=%s", user.id, label)
            raise exc

    for sender in watched_senders:
        sources.append(f"sender:{sender}")
        try:
            for parsed in svc.poll_sender_messages(
                db,
                user,
                sender,
                newer_than_days=lookback,
                processed_ids=processed_set,
                exclude_processed=False,
            ):
                by_id[parsed.message_id] = parsed
        except Exception as exc:
            logger.exception("Gmail sender poll failed user=%s sender=%s", user.id, sender)
            raise exc

    for watch in watched_threads:
        thread_id = watch.get("thread_id") if isinstance(watch, dict) else None
        if not thread_id:
            continue
        sources.append(f"thread:{thread_id}")
        try:
            for parsed in svc.poll_watched_thread_messages(
                db, user, thread_id, processed_ids=processed_set
            ):
                by_id[parsed.message_id] = parsed
        except Exception as exc:
            logger.exception("Gmail thread poll failed user=%s thread=%s", user.id, thread_id)
            raise exc

    return list(by_id.values()), sources


def _thread_summary_for_message(
    db: Session,
    user: User,
    parsed: ParsedEmail,
    settings: GmailSettings,
) -> str:
    svc = get_gmail_service()
    watched_thread_ids = {
        w.get("thread_id")
        for w in (settings.watched_threads or [])
        if isinstance(w, dict) and w.get("thread_id")
    }
    watched_senders = {s.lower() for s in (settings.watched_senders or [])}
    sender_match = parsed.sender_email.lower() in watched_senders if parsed.sender_email else False
    thread_match = parsed.thread_id in watched_thread_ids
    if not sender_match and not thread_match:
        return ""
    try:
        messages = svc.get_thread(db, user, parsed.thread_id)
        ctx = svc.thread_context_for_ai(messages, parsed.message_id)
        return ctx.get("prior_summary", "")
    except Exception:
        return ""


def _maybe_autodraft_reply(
    db: Session,
    user: User,
    parsed: ParsedEmail,
    task: Task,
    thread_summary: str,
) -> bool:
    """Auto-generate a reply draft for high-priority (P0/P1) tasks, awaiting user approval.

    Returns True if a draft was created. Failures are swallowed by the caller so a
    draft error never blocks task ingestion.
    """
    if task.priority not in AUTODRAFT_PRIORITIES:
        return False

    existing = db.execute(
        select(EmailDraft.id).where(
            EmailDraft.user_id == user.id,
            EmailDraft.gmail_message_id == parsed.message_id,
        ).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return False

    result = orch_tasks.generate_email_reply(
        latest_body=parsed.body or parsed.snippet or "",
        original_subject=parsed.subject,
        from_addr=parsed.from_addr,
        prior_summary=thread_summary,
        user_feedback=None,
        module="gmail",
        operation="autodraft_reply",
        user_id=user.id,
        db=db,
    )

    draft = EmailDraft(
        user_id=user.id,
        task_id=task.id,
        auto_generated=True,
        gmail_thread_id=parsed.thread_id,
        gmail_message_id=parsed.message_id,
        original_subject=parsed.subject,
        original_body=(parsed.body or parsed.snippet or "")[:12000],
        from_addr=parsed.from_addr,
        to_addr=parsed.sender_email or parsed.from_addr,
        draft_subject=result.subject,
        draft_body=result.body,
        status="draft",
        model_version=result.model_version,
    )
    db.add(draft)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="email_draft_autogenerated",
        module="gmail",
        input_summary=parsed.subject[:300],
        ai_output_summary=result.body[:300],
        confidence_score=result.confidence,
        model_version=result.model_version,
        target_id=draft.id,
    )
    return True


def poll_user_gmail(
    db: Session, user: User, *, force_ingest: bool = False, msa_only: bool = False
) -> dict:
    """Poll Gmail for one user: task ingest + MSA vendor returns."""
    svc = get_gmail_service()
    summary: dict = {
        "tasks_created": 0,
        "drafts_created": 0,
        "messages_scanned": 0,
        "skipped": 0,
        "msa_processed": 0,
        "msa_ingested": [],
        "msa_auto_created": [],
        "msa_skipped": 0,
        "sources": [],
        "hint": None,
        "errors": [],
    }

    cred = db.execute(
        select(GmailCredential).where(GmailCredential.user_id == user.id)
    ).scalar_one_or_none()
    if cred is None:
        summary["hint"] = "Gmail not connected — connect in Settings first."
        return summary

    settings = get_or_create_settings(db, user.id)
    processed_set = set(settings.processed_message_ids or [])

    should_ingest = not msa_only and (force_ingest or (settings.poll_enabled and settings.auto_task_ingest))

    if should_ingest:
        try:
            messages, sources = _collect_poll_messages(
                db, user, settings, processed_set, force_ingest=force_ingest
            )
            summary["sources"] = sources
            summary["messages_scanned"] = len(messages)

            if not messages:
                if not sources:
                    summary["hint"] = (
                        "No watched threads/senders/labels configured. Add a watch in Settings "
                        "(or use 'Ingest tasks' on a specific email) to create tasks."
                    )
                else:
                    summary["hint"] = (
                        f"No messages found in the last {settings.poll_lookback_days or 7} days "
                        f"for configured sources."
                    )

            unprocessed = [m for m in messages if m.message_id not in processed_set]
            summary["skipped"] = len(messages) - len(unprocessed)
            ingested_this_poll = 0
            for parsed in unprocessed:
                if ingested_this_poll >= MAX_INGEST_PER_POLL:
                    break
                thread_summary = _thread_summary_for_message(db, user, parsed, settings)
                try:
                    result = ingest_email_as_tasks(
                        db,
                        user,
                        parsed,
                        thread_summary=thread_summary,
                        allow_fallback=force_ingest or settings.auto_task_ingest,
                    )
                except Exception as exc:
                    db.rollback()
                    logger.exception("Ingest failed message=%s user=%s", parsed.message_id, user.id)
                    summary["errors"].append(f"message:{parsed.message_id}:{exc}")
                    continue
                ingested_this_poll += 1
                if result.tasks:
                    summary["tasks_created"] += len(result.tasks)
                    for task in result.tasks:
                        try:
                            if _maybe_autodraft_reply(db, user, parsed, task, thread_summary):
                                summary["drafts_created"] += 1
                        except Exception as exc:
                            logger.exception(
                                "Auto-draft failed task=%s message=%s user=%s",
                                task.id,
                                parsed.message_id,
                                user.id,
                            )
                            summary["errors"].append(f"autodraft:{parsed.message_id}:{exc}")
                elif result.should_mark_processed:
                    summary["skipped"] += 1
                if result.should_mark_processed:
                    processed_set.add(parsed.message_id)
                    settings.processed_message_ids = mark_message_processed(
                        settings.processed_message_ids or [],
                        parsed.message_id,
                    )
                db.commit()

            if len(unprocessed) > ingested_this_poll and ingested_this_poll >= MAX_INGEST_PER_POLL:
                summary["hint"] = (
                    f"Ingested {ingested_this_poll} of {len(unprocessed)} unprocessed email(s) this run. "
                    "Poll again to process more."
                )
        except Exception as exc:
            db.rollback()
            logger.exception("Gmail task poll failed for user %s", user.id)
            summary["errors"].append(f"ingest:{exc}")

    try:
        from app.services.msa_gmail_ingest_service import poll_msa_vendor_threads

        msa_result = poll_msa_vendor_threads(db, user)
        summary["msa_processed"] = len(msa_result.get("ingested", [])) + len(
            msa_result.get("auto_created", [])
        )
        summary["msa_ingested"] = msa_result.get("ingested", [])
        summary["msa_auto_created"] = msa_result.get("auto_created", [])
        summary["msa_skipped"] = msa_result.get("skipped", 0)
        if msa_result.get("errors"):
            summary["errors"].extend(msa_result["errors"])
    except Exception as exc:
        logger.exception("Gmail MSA poll failed for user %s", user.id)
        summary["errors"].append(f"msa:{exc}")

    try:
        summary["reminders_created"] = process_draft_reminders(db, user)
    except Exception as exc:
        logger.exception("Gmail draft reminders failed for user %s", user.id)
        summary["errors"].append(f"reminders:{exc}")

    settings.last_poll_at = datetime.now(timezone.utc)
    db.commit()
    return summary


def process_draft_reminders(db: Session, user: User) -> int:
    """Create reminder tasks for approved drafts past remind_at."""
    now = datetime.now(timezone.utc)
    due = (
        db.execute(
            select(EmailDraft).where(
                EmailDraft.user_id == user.id,
                EmailDraft.status == "approved",
                EmailDraft.remind_at.is_not(None),
                EmailDraft.remind_at <= now,
            )
        )
        .scalars()
        .all()
    )
    created = 0
    for draft in due:
        existing = db.execute(
            select(Task).where(
                Task.created_by_id == user.id,
                Task.source == "email",
                Task.source_module == "gmail_draft",
                Task.source_ref_id == draft.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        t = Task(
            title=f"Send approved reply: {draft.draft_subject[:100]}",
            description=f"AI draft approved — send reply to {draft.to_addr or draft.from_addr}.",
            source="email",
            source_module="gmail_draft",
            source_ref_id=draft.id,
            email_sender=draft.from_addr,
            email_subject=draft.draft_subject,
            email_body=draft.draft_body[:6000],
            gmail_thread_id=draft.gmail_thread_id,
            priority="P1",
            priority_score=0.85,
            status="todo",
            tags=["gmail", "send-reminder"],
            created_by_id=user.id,
            assigned_to_id=user.id,
        )
        db.add(t)
        draft.remind_at = None
        created += 1
    if created:
        db.commit()
    return created
