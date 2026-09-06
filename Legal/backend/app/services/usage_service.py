"""LLM usage capture for governance metrics."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Generator

from sqlalchemy.orm import Session

from app.models.llm_usage import LLMUsageLog


@dataclass
class UsageContext:
    db: Session | None = None
    user_id: int | None = None
    module: str = "unknown"
    operation: str = "unknown"
    agent_name: str | None = None
    model_version: str | None = None
    audit_log_id: int | None = None


_current_ctx: ContextVar[UsageContext | None] = ContextVar("usage_ctx", default=None)


def get_usage_context() -> UsageContext | None:
    return _current_ctx.get()


@contextmanager
def usage_context(
    db: Session,
    *,
    user_id: int | None,
    module: str,
    operation: str,
    model_version: str | None = None,
    agent_name: str | None = None,
) -> Generator[UsageContext, None, None]:
    ctx = UsageContext(
        db=db,
        user_id=user_id,
        module=module,
        operation=operation,
        agent_name=agent_name,
        model_version=model_version,
    )
    token = _current_ctx.set(ctx)
    try:
        yield ctx
    finally:
        _current_ctx.reset(token)


def estimate_tokens_from_chars(char_count: int) -> int:
    """Rough token estimate when provider metadata is unavailable."""
    return max(1, char_count // 4) if char_count > 0 else 0


def record_llm_call(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int | None = None,
    latency_ms: int | None = None,
    model_version: str | None = None,
    estimated: bool = False,
    audit_log_id: int | None = None,
) -> LLMUsageLog | None:
    """Persist one LLM invocation. Uses contextvars when db/user/module omitted."""
    ctx = get_usage_context()
    if ctx is None or ctx.db is None:
        return None

    resolved_total = total_tokens if total_tokens is not None else input_tokens + output_tokens
    entry = LLMUsageLog(
        user_id=ctx.user_id,
        module=ctx.module,
        operation=ctx.operation,
        agent_name=ctx.agent_name,
        model_version=model_version or ctx.model_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=resolved_total,
        latency_ms=latency_ms,
        estimated=estimated,
        audit_log_id=audit_log_id or ctx.audit_log_id,
    )
    ctx.db.add(entry)
    ctx.db.flush()
    return entry


def attach_audit_log_id(audit_log_id: int) -> None:
    """Link subsequent usage rows to the audit entry for this request."""
    ctx = get_usage_context()
    if ctx is not None:
        ctx.audit_log_id = audit_log_id
