"""AI call tracing — persist one AiCall row per model call with cost & latency.

Callers measure latency and pass token usage; cost is derived here from pricing
so every traced call carries real spend. Logging never raises into the caller:
a failed insert is swallowed (tracing must not break the feature it traces)."""

import uuid

import logging

from sqlalchemy.orm import Session

from app.models.ai_call import AiCall
from app.services import pricing

logger = logging.getLogger("uvicorn.error")


def record_call(
    db: Session,
    *,
    operation: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    brief_id: uuid.UUID | None = None,
    creative_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    status: str = "ok",
    error: str | None = None,
    commit: bool = True,
) -> AiCall | None:
    """Write one traced call. Returns the row, or None if logging failed."""
    total = (input_tokens or 0) + (output_tokens or 0)
    try:
        row = AiCall(
            operation=operation,
            model=model,
            brief_id=brief_id,
            creative_id=creative_id,
            actor_id=actor_id,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
            total_tokens=total,
            latency_ms=latency_ms or 0,
            cost_inr=pricing.cost_inr(model, input_tokens or 0, output_tokens or 0),
            status=status,
            error=error,
        )
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        return row
    except Exception:  # noqa: BLE001 — tracing must never break the traced call
        logger.exception("Failed to record AI call trace (%s/%s)", operation, model)
        db.rollback()
        return None
