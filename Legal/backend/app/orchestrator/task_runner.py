"""Single-shot structured agent runs (non-streaming).

Shared path for MSA / Gmail / review / research / news:
  armor (PII + input screen) → ADK InMemoryRunner → sanitize → metrics.

Chat SSE stays in ``pipeline.py``. Discrete product actions never use LLM
transfer — the caller picks the agent via ``rules.classify``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, TypeVar

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adk.runner import _run_coro
from app.config import settings
from app.orchestrator import config as orch_config
from app.orchestrator.guardrails import mask_pii, restore_pii, sanitize_output, screen_input
from app.orchestrator.guardrails.armor import REFUSAL_MESSAGE
from app.orchestrator.metrics import record_llm_call, task_usage
from app.orchestrator.rules import AgentId
from app.services.usage_service import estimate_tokens_from_chars

logger = logging.getLogger("legalos.orchestrator")

T = TypeVar("T", bound=BaseModel)

_APP = "legalos_tasks"


class TaskBlockedError(RuntimeError):
    """Raised when input armor blocks the request."""

    def __init__(self, message: str = REFUSAL_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


async def _arun_text(agent: LlmAgent, prompt: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=_APP)
    sid = uuid.uuid4().hex
    await runner.session_service.create_session(
        app_name=_APP, user_id="task", session_id=sid
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(
        user_id="task", session_id=sid, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)
    return final_text


def run_structured(
    *,
    agent: LlmAgent,
    agent_id: AgentId | str,
    prompt: str,
    schema: type[T],
    module: str,
    operation: str,
    user_id: int | None = None,
    db: Session | None = None,
) -> T:
    """Armor → run agent → parse JSON into ``schema`` → record tokens."""
    combined = prompt
    masked, pii_map = (
        mask_pii(combined) if orch_config.PII_MASKING_ENABLED else (combined, {})
    )
    verdict = screen_input(masked, enabled=orch_config.ARMOR_ENABLED)
    if verdict.blocked:
        raise TaskBlockedError(REFUSAL_MESSAGE)

    model_repr = type(agent.model).__name__ if not isinstance(agent.model, str) else agent.model
    start = time.perf_counter()
    with task_usage(
        db,
        user_id=user_id,
        module=module,
        operation=operation,
        agent_name=str(agent_id),
        model_version=model_repr,
    ):
        try:
            raw = _run_coro(_arun_text(agent, masked))
        except Exception:
            logger.exception("task_runner failed agent=%s", agent_id)
            raise
        latency_ms = int((time.perf_counter() - start) * 1000)
        cleaned = restore_pii(sanitize_output(raw), pii_map).strip()
        record_llm_call(
            input_tokens=estimate_tokens_from_chars(len(masked)),
            output_tokens=estimate_tokens_from_chars(len(cleaned)),
            latency_ms=latency_ms,
            model_version=model_repr,
            estimated=True,
        )

    if not cleaned:
        raise ValueError(f"Agent {agent_id} returned empty response")
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
    try:
        data: Any = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent {agent_id} returned non-JSON: {exc}") from exc
    return schema.model_validate(data)


def run_text(
    *,
    agent: LlmAgent,
    agent_id: AgentId | str,
    prompt: str,
    module: str,
    operation: str,
    user_id: int | None = None,
    db: Session | None = None,
) -> str:
    """Armor → run agent → return plain text → record tokens."""
    masked, pii_map = (
        mask_pii(prompt) if orch_config.PII_MASKING_ENABLED else (prompt, {})
    )
    verdict = screen_input(masked, enabled=orch_config.ARMOR_ENABLED)
    if verdict.blocked:
        raise TaskBlockedError(REFUSAL_MESSAGE)

    model_repr = type(agent.model).__name__ if not isinstance(agent.model, str) else agent.model
    start = time.perf_counter()
    with task_usage(
        db,
        user_id=user_id,
        module=module,
        operation=operation,
        agent_name=str(agent_id),
        model_version=model_repr,
    ):
        raw = _run_coro(_arun_text(agent, masked))
        latency_ms = int((time.perf_counter() - start) * 1000)
        cleaned = restore_pii(sanitize_output(raw), pii_map).strip()
        record_llm_call(
            input_tokens=estimate_tokens_from_chars(len(masked)),
            output_tokens=estimate_tokens_from_chars(len(cleaned)),
            latency_ms=latency_ms,
            model_version=model_repr,
            estimated=True,
        )
    return cleaned


def is_stub_backend() -> bool:
    return settings.ai_backend.lower() == "stub"
