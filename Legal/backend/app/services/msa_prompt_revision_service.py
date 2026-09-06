"""MSA prompt-edit revision persistence and edit memory."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.msa_prompt_revision import MSAPromptRevision
from app.services.ai_service import DocxOperationItem
from app.services.negotiation_memory_service import list_memory


def operation_to_dict(op: DocxOperationItem) -> dict:
    return {
        "op_type": op.op_type,
        "anchor_id": op.anchor_id,
        "after_anchor_id": op.after_anchor_id,
        "target_text": op.target_text,
        "content": op.content,
        "description": op.description,
        "confidence": op.confidence,
    }


def get_edit_memory(db: Session, tracker_id: int, limit: int = 5) -> list[str]:
    """Return summaries of recent negotiation context for multi-turn edits."""
    mem_rows = list_memory(db, tracker_id, limit=limit * 3)
    snippets: list[str] = []
    for row in reversed(mem_rows):
        if row.kind in ("edit_summary", "decision", "guideline", "bot_qa"):
            text = row.content[:400]
            if text and text not in snippets:
                snippets.append(text)
        if len(snippets) >= limit:
            break
    if snippets:
        return snippets

    rows = (
        db.execute(
            select(MSAPromptRevision)
            .where(
                MSAPromptRevision.tracker_id == tracker_id,
                MSAPromptRevision.status == "applied",
            )
            .order_by(MSAPromptRevision.applied_at.desc(), MSAPromptRevision.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    summaries: list[str] = []
    for row in reversed(rows):
        if row.change_summary:
            summaries.append(row.change_summary)
        elif row.instruction:
            summaries.append(row.instruction[:300])
    return summaries


def list_prompt_revisions(db: Session, tracker_id: int) -> list[MSAPromptRevision]:
    return list(
        db.execute(
            select(MSAPromptRevision)
            .where(MSAPromptRevision.tracker_id == tracker_id)
            .order_by(MSAPromptRevision.created_at.desc())
        )
        .scalars()
        .all()
    )
