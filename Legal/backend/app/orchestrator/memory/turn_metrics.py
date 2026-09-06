"""Durable per-turn logging + session index helpers.

Synchronous (regular `Session`) helpers. The async chat pipeline calls
`record_turn` / `upsert_session` inside `anyio.to_thread.run_sync` with a
fresh session, keeping ORM work off the event loop. Read helpers back the
sidebar and history replay.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chat import ChatSession, ChatTurn
from app.orchestrator.models import SessionSummary, TurnOut


def _title_from_text(text: str) -> str:
    snippet = " ".join(text.strip().split())
    return (snippet[:60] + "…") if len(snippet) > 60 else (snippet or "New Chat Session")


def upsert_session(db: Session, session_id: str, user_id: int, first_text: str) -> ChatSession:
    """Create the sidebar record on the first turn; bump activity thereafter."""
    row = db.get(ChatSession, session_id)
    if row is None:
        row = ChatSession(
            session_id=session_id,
            user_id=user_id,
            title=_title_from_text(first_text),
        )
        db.add(row)
    db.flush()
    return row


def record_turn(
    db: Session,
    *,
    session_id: str,
    user_id: int,
    user_query: str,
    bot_response: str,
    agent_name: str | None,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int | None,
    blocked: bool,
    sources: list[dict[str, Any]] | None = None,
    thoughts: list[dict[str, Any]] | None = None,
    mode: str | None = None,
) -> ChatTurn:
    turn = ChatTurn(
        session_id=session_id,
        user_id=user_id,
        user_query=user_query,
        bot_response=bot_response,
        agent_name=agent_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        blocked=blocked,
        sources=sources or None,
        thoughts=thoughts or None,
        mode=mode,
    )
    db.add(turn)
    db.flush()
    return turn


def list_sessions(db: Session, user_id: int, limit: int = 50) -> list[SessionSummary]:
    rows = (
        db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    summaries: list[SessionSummary] = []
    for s in rows:
        last = db.execute(
            select(ChatTurn)
            .where(ChatTurn.session_id == s.session_id)
            .order_by(ChatTurn.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        count = db.execute(
            select(func.count(ChatTurn.id)).where(ChatTurn.session_id == s.session_id)
        ).scalar_one()
        summaries.append(
            SessionSummary(
                session_id=s.session_id,
                title=s.title,
                last_message_preview=(last.user_query[:120] if last else None),
                turn_count=int(count or 0),
                updated_at=s.updated_at.isoformat() if s.updated_at else None,
            )
        )
    return summaries


def replay_turns(db: Session, session_id: str) -> list[TurnOut]:
    """Return the flattened user/assistant message list for a session.

    Access is enforced by the caller (owner or shared-with) before this is
    invoked; here we return every turn in the session in order.
    """
    rows = (
        db.execute(
            select(ChatTurn)
            .where(ChatTurn.session_id == session_id)
            .order_by(ChatTurn.id.asc())
        )
        .scalars()
        .all()
    )
    out: list[TurnOut] = []
    for t in rows:
        ts = t.created_at.isoformat() if t.created_at else None
        out.append(TurnOut(role="user", text=t.user_query, created_at=ts))
        if t.bot_response:
            out.append(
                TurnOut(
                    role="assistant",
                    text=t.bot_response,
                    created_at=ts,
                    turn_id=t.id,
                    sources=t.sources or [],
                    thoughts=t.thoughts or [],
                    mode=t.mode,  # type: ignore[arg-type]
                    feedback=_feedback_label(t.feedback),
                    feedback_comment=t.feedback_comment,
                )
            )
    return out


def _feedback_label(value: int | None) -> str | None:
    if value == 1:
        return "up"
    if value == -1:
        return "down"
    return None


def load_history_text(db: Session, session_id: str, user_id: int, turns: int) -> str:
    """A compact plain-text transcript of the last `turns` exchanges.

    Injected as fallback context; the ADK session already carries structured
    history, so this is a belt-and-braces summary for the model prompt.
    """
    rows = (
        db.execute(
            select(ChatTurn)
            .where(ChatTurn.session_id == session_id, ChatTurn.user_id == user_id)
            .order_by(ChatTurn.id.desc())
            .limit(turns)
        )
        .scalars()
        .all()
    )
    if not rows:
        return ""
    lines: list[str] = []
    for t in reversed(rows):
        lines.append(f"User: {t.user_query}")
        if t.bot_response:
            lines.append(f"Assistant: {t.bot_response}")
    return "\n".join(lines)
