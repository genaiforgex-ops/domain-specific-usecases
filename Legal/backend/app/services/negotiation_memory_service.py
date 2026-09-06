"""Negotiation memory capture and retrieval for MSA trackers."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.negotiation_memory import NegotiationMemory


def append_memory(
    db: Session,
    *,
    tracker_id: int,
    kind: str,
    content: str,
    user_id: int | None = None,
    version_id: int | None = None,
) -> NegotiationMemory:
    row = NegotiationMemory(
        tracker_id=tracker_id,
        kind=kind,
        content=content,
        created_by_id=user_id,
        version_id=version_id,
    )
    db.add(row)
    db.flush()
    return row


def list_memory(db: Session, tracker_id: int, limit: int = 50) -> list[NegotiationMemory]:
    return list(
        db.execute(
            select(NegotiationMemory)
            .where(NegotiationMemory.tracker_id == tracker_id)
            .order_by(NegotiationMemory.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )


def memory_snippets(db: Session, tracker_id: int, limit: int = 8) -> list[str]:
    rows = list_memory(db, tracker_id, limit=limit)
    snippets: list[str] = []
    for row in reversed(rows):
        prefix = row.kind.replace("_", " ").title()
        snippets.append(f"[{prefix}] {row.content[:500]}")
    return snippets


def record_guidelines(db: Session, tracker_id: int, guidelines: str | None, user_id: int) -> None:
    if not guidelines or not guidelines.strip():
        return
    append_memory(
        db,
        tracker_id=tracker_id,
        kind="guideline",
        content=guidelines.strip(),
        user_id=user_id,
    )


def record_decision(
    db: Session,
    tracker_id: int,
    *,
    suggestion_id: int,
    decision: str,
    user_id: int,
) -> None:
    append_memory(
        db,
        tracker_id=tracker_id,
        kind="decision",
        content=json.dumps({"suggestion_id": suggestion_id, "decision": decision}),
        user_id=user_id,
    )


def record_edit_summary(
    db: Session,
    tracker_id: int,
    summary: str,
    user_id: int,
    version_id: int | None = None,
) -> None:
    if not summary.strip():
        return
    append_memory(
        db,
        tracker_id=tracker_id,
        kind="edit_summary",
        content=summary.strip()[:2000],
        user_id=user_id,
        version_id=version_id,
    )


def record_bot_qa(
    db: Session,
    tracker_id: int,
    question: str,
    answer: str,
    user_id: int,
    version_id: int | None = None,
) -> None:
    append_memory(
        db,
        tracker_id=tracker_id,
        kind="bot_qa",
        content=json.dumps({"q": question[:500], "a": (answer or "")[:1000]}),
        user_id=user_id,
        version_id=version_id,
    )
