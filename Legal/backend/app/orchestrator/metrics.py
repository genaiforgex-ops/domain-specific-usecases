"""Unified token / governance recording for orchestrator runs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.services.usage_service import UsageContext, record_llm_call, usage_context


@contextmanager
def task_usage(
    db: Session | None,
    *,
    user_id: int | None,
    module: str,
    operation: str,
    agent_name: str,
    model_version: str | None = None,
) -> Generator[UsageContext, None, None]:
    """Like ``usage_context`` but also stamps ``agent_name`` on recorded rows."""
    if db is None:
        # No DB session — yield a dummy context; record_llm_call will no-op.
        yield UsageContext(
            db=None,
            user_id=user_id,
            module=module,
            operation=operation,
            model_version=model_version,
            agent_name=agent_name,
        )
        return
    with usage_context(
        db,
        user_id=user_id,
        module=module,
        operation=operation,
        model_version=model_version,
        agent_name=agent_name,
    ) as ctx:
        yield ctx


__all__ = ["task_usage", "record_llm_call"]
