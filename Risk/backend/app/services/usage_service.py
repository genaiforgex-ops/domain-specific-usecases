"""Best-effort recording of AI token usage.

Called from the AI choke points (M1 gateway, M2 OSINT). Deliberately swallows its
own errors: usage accounting is secondary to the actual model call, so a logging
problem must never surface as a failed classification or due-diligence run.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import LLMUsageLog

logger = logging.getLogger(__name__)


async def record_llm_usage(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    module: str,
    operation: str,
    model_version: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    latency_ms: int | None = None,
    agent_name: str | None = None,
    vendor_id=None,
) -> None:
    try:
        db.add(
            LLMUsageLog(
                actor_id=actor_id,
                module=module,
                operation=operation,
                agent_name=agent_name,
                vendor_id=vendor_id,
                model_version=model_version,
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
                total_tokens=total_tokens or 0,
                latency_ms=latency_ms,
            )
        )
        await db.flush()
    except Exception:  # noqa: BLE001 — usage logging must never break the AI call
        logger.warning("Failed to record LLM usage (%s/%s)", module, operation, exc_info=True)
