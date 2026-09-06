"""Audit log writer.

Single helper so every AI action and human decision routes through the same
schema. Append-only by convention — no module ever updates or deletes a row.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def write_audit(
    db: Session,
    *,
    user: User | None,
    action_type: str,
    module: str,
    input_summary: str | None = None,
    ai_output_summary: str | None = None,
    confidence_score: float | None = None,
    human_decision: str | None = None,
    model_version: str | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    target_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        role=user.role if user else "anonymous",
        action_type=action_type,
        module=module,
        input_summary=_truncate(input_summary, 2000),
        ai_output_summary=_truncate(ai_output_summary, 2000),
        confidence_score=confidence_score,
        human_decision=human_decision,
        model_version=model_version,
        ip_address=ip_address,
        session_id=session_id,
        target_id=target_id,
        extra=extra,
    )
    db.add(entry)
    db.flush()
    return entry


def _truncate(s: str | None, limit: int) -> str | None:
    if s is None:
        return None
    return s if len(s) <= limit else s[: limit - 3] + "..."
