"""Sharing, access control, deletion, and DOCX export for chat sessions.

Kept out of the SSE pipeline; these are ordinary synchronous DB operations the
REST router calls. Access rule: a session is readable by its owner and by any
user it has been shared with (read-only). Only the owner may share or delete.
"""

from __future__ import annotations

import io

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.chat import ChatSession, ChatShare, ChatTurn
from app.models.user import User
from app.orchestrator.models import SessionSummary, ShareResult


def session_owner(db: Session, session_id: str) -> int | None:
    row = db.get(ChatSession, session_id)
    return row.user_id if row else None


def can_access(db: Session, session_id: str, user_id: int) -> bool:
    owner = session_owner(db, session_id)
    if owner is None:
        return False
    if owner == user_id:
        return True
    share = db.execute(
        select(ChatShare.id).where(
            ChatShare.session_id == session_id,
            ChatShare.shared_with_user_id == user_id,
        )
    ).first()
    return share is not None


def list_session_shares(db: Session, session_id: str, owner_id: int) -> list[dict]:
    """Current shares for a session (owner only)."""
    owner = session_owner(db, session_id)
    if owner != owner_id:
        return []
    rows = db.execute(
        select(ChatShare, User)
        .join(User, User.id == ChatShare.shared_with_user_id)
        .where(ChatShare.session_id == session_id)
        .order_by(ChatShare.created_at.asc())
    ).all()
    out: list[dict] = []
    for share, u in rows:
        out.append(
            {
                "user_id": u.id,
                "email": u.email,
                "full_name": u.full_name or u.email,
                "shared_at": share.created_at.isoformat() if share.created_at else None,
            }
        )
    return out


def revoke_share(db: Session, session_id: str, owner_id: int, shared_with_user_id: int) -> bool:
    """Remove one share. Returns True if a row was deleted."""
    if session_owner(db, session_id) != owner_id:
        return False
    result = db.execute(
        delete(ChatShare).where(
            ChatShare.session_id == session_id,
            ChatShare.shared_with_user_id == shared_with_user_id,
        )
    )
    db.flush()
    return (result.rowcount or 0) > 0


def share_session(db: Session, session_id: str, owner_id: int, emails: list[str]) -> ShareResult:
    """Share a session with users by email (owner only). Idempotent per user."""
    from app.services.notify_hooks import notify_chat_shared

    result = ShareResult()
    owner = db.get(User, owner_id)
    owner_name = (owner.full_name if owner else None) or "A colleague"
    session_row = db.get(ChatSession, session_id)
    chat_title = session_row.title if session_row else "a chat"

    for email in {e.strip().lower() for e in emails if e.strip()}:
        target = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if target is None:
            result.not_found.append(email)
            continue
        if target.id == owner_id:
            continue  # sharing with yourself is a no-op
        exists = db.execute(
            select(ChatShare.id).where(
                ChatShare.session_id == session_id,
                ChatShare.shared_with_user_id == target.id,
            )
        ).first()
        if not exists:
            db.add(
                ChatShare(
                    session_id=session_id,
                    shared_by_user_id=owner_id,
                    shared_with_user_id=target.id,
                )
            )
            # Notify only on a NEW share (not idempotent re-shares).
            notify_chat_shared(db, target, owner_name, chat_title, session_id)
        result.shared_with.append(email)
    db.flush()
    return result


def list_shared_with_me(db: Session, user_id: int) -> list[SessionSummary]:
    rows = db.execute(
        select(ChatSession, User.full_name)
        .join(ChatShare, ChatShare.session_id == ChatSession.session_id)
        .join(User, User.id == ChatShare.shared_by_user_id)
        .where(ChatShare.shared_with_user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    ).all()
    out: list[SessionSummary] = []
    for s, owner_name in rows:
        out.append(
            SessionSummary(
                session_id=s.session_id,
                title=s.title,
                turn_count=0,
                updated_at=s.updated_at.isoformat() if s.updated_at else None,
                shared_by=owner_name,
            )
        )
    return out


def delete_session_data(db: Session, session_id: str) -> None:
    """Remove the app-owned rows for a session (turns, shares, index).

    The ADK-owned conversation events are deleted separately by the async route
    via the session service.
    """
    db.execute(delete(ChatShare).where(ChatShare.session_id == session_id))
    db.execute(delete(ChatTurn).where(ChatTurn.session_id == session_id))
    db.execute(delete(ChatSession).where(ChatSession.session_id == session_id))
    db.flush()


def export_session_docx(db: Session, session_id: str) -> tuple[bytes, str]:
    """Render a session's transcript to a .docx. Returns (bytes, filename)."""
    from docx import Document

    session = db.get(ChatSession, session_id)
    title = session.title if session else "LawGenie Chat"
    turns = (
        db.execute(select(ChatTurn).where(ChatTurn.session_id == session_id).order_by(ChatTurn.id.asc()))
        .scalars()
        .all()
    )

    doc = Document()
    doc.add_heading(title, level=1)
    doc.add_paragraph("LawGenie — LegalOS Assistant transcript").italic = True
    for t in turns:
        h = doc.add_paragraph()
        run = h.add_run("You")
        run.bold = True
        doc.add_paragraph(t.user_query)
        if t.bot_response:
            h2 = doc.add_paragraph()
            run2 = h2.add_run("LawGenie")
            run2.bold = True
            doc.add_paragraph(t.bot_response)
        doc.add_paragraph("")

    buf = io.BytesIO()
    doc.save(buf)
    safe = "".join(c for c in title if c.isalnum() or c in " -_")[:50].strip() or "chat"
    return buf.getvalue(), f"{safe}.docx"


def export_turn_docx(turn: ChatTurn) -> tuple[bytes, str]:
    """Render a single assistant answer (with its question) to a .docx."""
    from docx import Document

    doc = Document()
    doc.add_heading("LawGenie answer", level=1)
    doc.add_paragraph("LawGenie — LegalOS Assistant").italic = True

    q = doc.add_paragraph()
    q.add_run("Question").bold = True
    doc.add_paragraph(turn.user_query)

    a = doc.add_paragraph()
    a.add_run("Answer").bold = True
    doc.add_paragraph(turn.bot_response or "")

    sources = turn.sources or []
    if sources:
        doc.add_paragraph("")
        doc.add_paragraph().add_run("References").bold = True
        for s in sources:
            title = str(s.get("title") or "").strip()
            url = str(s.get("url") or "").strip()
            site = str(s.get("site") or "").strip()
            label = f"{site} — {title}" if site else title
            doc.add_paragraph(f"{label} {url}".strip(), style="List Bullet")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), f"lawgenie-answer-{turn.id}.docx"
