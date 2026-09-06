"""Sync bridge over ADK's async API.

The service layer and FastAPI `def` handlers are synchronous, so we drive the
agent with `asyncio.run` and a fresh in-memory session per call (stateless —
each extraction is independent)."""

import asyncio
import json

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.adk.agents import build_brief_creator_agent, build_creative_agent
from app.adk.models import configure_genai

_APP_NAME = "brief_creator"
_CREATIVE_APP_NAME = "creative_agent"


def _accumulate_usage(event, usage: dict) -> None:
    """Fold an ADK event's token usage into the running totals (last non-null wins —
    ADK reports cumulative counts, so the latest event carries the call total)."""
    um = getattr(event, "usage_metadata", None)
    if not um:
        return
    prompt = getattr(um, "prompt_token_count", None)
    candidates = getattr(um, "candidates_token_count", None)
    if prompt is not None:
        usage["input_tokens"] = prompt
    if candidates is not None:
        usage["output_tokens"] = candidates


async def _run(brief_type: str, raw_text: str, extra_instruction: str | None) -> tuple[dict, dict]:
    agent = build_brief_creator_agent(brief_type, extra_instruction)
    runner = InMemoryRunner(agent=agent, app_name=_APP_NAME)
    await runner.session_service.create_session(
        app_name=_APP_NAME, user_id="bc", session_id="s1"
    )
    message = types.Content(role="user", parts=[types.Part(text=raw_text)])

    final_text = ""
    usage = {"input_tokens": 0, "output_tokens": 0}
    async for event in runner.run_async(user_id="bc", session_id="s1", new_message=message):
        _accumulate_usage(event, usage)
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""

    data = json.loads(final_text) if final_text else {}
    # Keep only non-empty string values.
    cleaned = {k: str(v).strip() for k, v in data.items() if isinstance(v, str) and v.strip()}
    return cleaned, usage


def run_brief_extraction(
    brief_type: str, raw_text: str, extra_instruction: str | None = None
) -> tuple[dict, dict]:
    configure_genai()
    return asyncio.run(_run(brief_type, raw_text, extra_instruction))


async def _run_creatives(prompt: str, extra_instruction: str | None) -> tuple[list[dict], dict]:
    agent = build_creative_agent(extra_instruction)
    runner = InMemoryRunner(agent=agent, app_name=_CREATIVE_APP_NAME)
    await runner.session_service.create_session(
        app_name=_CREATIVE_APP_NAME, user_id="st", session_id="s1"
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    final_text = ""
    usage = {"input_tokens": 0, "output_tokens": 0}
    async for event in runner.run_async(user_id="st", session_id="s1", new_message=message):
        _accumulate_usage(event, usage)
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or ""

    data = json.loads(final_text) if final_text else {}
    creatives = data.get("creatives", []) if isinstance(data, dict) else []
    return [c for c in creatives if isinstance(c, dict) and c.get("headline") and c.get("body")], usage


def run_creative_generation(
    prompt: str, extra_instruction: str | None = None
) -> tuple[list[dict], dict]:
    configure_genai()
    return asyncio.run(_run_creatives(prompt, extra_instruction))
