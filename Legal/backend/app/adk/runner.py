"""Sync bridge for running an ADK agent on a single prompt.

ADK is async-first (`create_session` is a coroutine, `run_async` an async
generator), but the LegalAIService interface is synchronous. This bridge must
work from two contexts:

  - FastAPI `def` handlers, which run in a worker thread with no running event
    loop — here `asyncio.run()` is safe.
  - The background Gmail poll loop (`asyncio.create_task` in main.py), which
    calls into this synchronously while the event loop is running — here
    `asyncio.run()` raises "cannot be called from a running event loop", so we
    offload the coroutine to a dedicated thread with its own loop instead.

`_run_coro` picks the right strategy automatically. Either way each call gets an
isolated, fresh in-memory session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, TypeVar

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

from app.services.usage_service import estimate_tokens_from_chars, record_llm_call

logger = logging.getLogger("legalos.adk")

_APP_NAME = "legalos"
_USER_ID = "legalos-service"
_SESSION_ID = "single-turn"

T = TypeVar("T", bound=BaseModel)


def _run_coro(coro: Coroutine[Any, Any, str]) -> str:
    """Run a coroutine to completion from a synchronous caller.

    Safe whether or not an event loop is already running on this thread: if one
    is (e.g. the background poll loop), the coroutine is executed in a separate
    thread with its own event loop so we never touch the running loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # An event loop is already running on this thread — offload to a fresh one.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _arun(agent: LlmAgent, prompt: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=_APP_NAME)
    await runner.session_service.create_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=_SESSION_ID
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(
        user_id=_USER_ID, session_id=_SESSION_ID, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)
    return final_text


def run_agent_text(agent: LlmAgent, prompt: str) -> str:
    """Run the agent and return its final response as plain text."""
    model_repr = type(agent.model).__name__ if not isinstance(agent.model, str) else agent.model
    logger.info(
        "ADK agent invoking: name=%s model=%s prompt_chars=%d",
        agent.name,
        model_repr,
        len(prompt),
    )
    start = time.perf_counter()
    try:
        out = _run_coro(_arun(agent, prompt))
    except Exception as exc:  # noqa: BLE001 — log then re-raise so callers can fall back
        logger.warning("ADK agent FAILED: name=%s model=%s error=%s", agent.name, model_repr, exc)
        raise
    latency_ms = int((time.perf_counter() - start) * 1000)
    logger.info("ADK agent returned: name=%s output_chars=%d", agent.name, len(out))
    record_llm_call(
        input_tokens=estimate_tokens_from_chars(len(prompt)),
        output_tokens=estimate_tokens_from_chars(len(out)),
        latency_ms=latency_ms,
        model_version=model_repr,
        estimated=True,
    )
    return out


def run_agent_structured(agent: LlmAgent, prompt: str, schema: type[T]) -> T:
    """Run an agent with an output_schema and parse the JSON into `schema`.

    Raises ValueError if the model returns text that does not validate — callers
    are expected to catch this and fall back to the deterministic stub.
    """
    raw = run_agent_text(agent, prompt).strip()
    if not raw:
        raise ValueError("ADK agent returned empty response")
    # Agents with output_schema return bare JSON, but strip markdown fences just in case.
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{") : raw.rfind("}") + 1]
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ADK agent returned non-JSON output: {exc}") from exc
    return schema.model_validate(data)
