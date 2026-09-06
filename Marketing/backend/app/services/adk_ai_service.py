"""ADK / Gemini implementation of the AI seam — the Brief Creator and Creative
Agents.

This is the only backend: there is no stub fallback. A missing API key, an agent
error, or empty output raises a RuntimeError so the caller can surface it instead
of silently returning canned content.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from app.config import settings
from app.services.ai_service import (
    AIService,
    BriefExtraction,
    CreativeGeneration,
    Usage,
)

logger = logging.getLogger("uvicorn.error")

_NO_KEY = "AI agent unavailable: GEMINI_API_KEY is not set."

# Gemini Flash occasionally returns transient errors (503 overloaded, 429 rate
# limit, deadline/timeout, 5xx) or JSON the parser rejects. Retry those a couple
# of times with backoff before surfacing the failure as a 502 to the caller.
_TRANSIENT_MARKERS = (
    "503", "overloaded", "unavailable", "429", "rate limit", "rate_limit",
    "resource_exhausted", "deadline", "timeout", "temporarily", "500",
    "internal error", "502", "504",
)
_RETRY_BACKOFF = (0.6, 1.8)  # seconds before attempts 2 and 3
_MAX_ATTEMPTS = len(_RETRY_BACKOFF) + 1

T = TypeVar("T")


def _is_transient(e: Exception) -> bool:
    if isinstance(e, json.JSONDecodeError):
        return True
    msg = f"{type(e).__name__} {e}".lower()
    return any(m in msg for m in _TRANSIENT_MARKERS)


def _with_retries(fn: Callable[[], T], what: str) -> T:
    """Call fn, retrying transient failures with backoff. Permanent errors and
    the final attempt's error propagate unchanged."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — classify then re-raise
            if attempt < _MAX_ATTEMPTS and _is_transient(e):
                delay = _RETRY_BACKOFF[attempt - 1]
                logger.warning(
                    "%s transient failure (attempt %d/%d): %s — retrying in %.1fs",
                    what, attempt, _MAX_ATTEMPTS, e, delay,
                )
                time.sleep(delay)
                continue
            raise
    raise AssertionError("unreachable")  # pragma: no cover


def _usage(raw: dict, started: float) -> Usage:
    return Usage(
        input_tokens=int(raw.get("input_tokens", 0) or 0),
        output_tokens=int(raw.get("output_tokens", 0) or 0),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


class ADKAIService(AIService):
    def extract_brief(
        self, raw_text: str, brief_type: str, prompt_append: str | None = None
    ) -> BriefExtraction:
        if not settings.gemini_api_key:
            raise RuntimeError(_NO_KEY)
        started = time.perf_counter()
        try:
            from app.adk.runner import run_brief_extraction

            values, raw_usage = _with_retries(
                lambda: run_brief_extraction(brief_type, raw_text, prompt_append),
                "Brief Creator Agent",
            )
        except Exception as e:  # noqa: BLE001 — re-raise as a clean service error
            logger.exception("Brief Creator Agent failed")
            raise RuntimeError(f"Brief Creator Agent failed: {e}") from e
        if not values:
            raise RuntimeError("Brief Creator Agent returned no fields.")
        return BriefExtraction(
            values=values, model_version=settings.gemini_model, usage=_usage(raw_usage, started)
        )

    def generate_creatives(
        self, prompt: str, count: int, prompt_append: str | None = None
    ) -> CreativeGeneration:
        if not settings.gemini_api_key:
            raise RuntimeError(_NO_KEY)
        started = time.perf_counter()
        try:
            from app.adk.runner import run_creative_generation

            creatives, raw_usage = _with_retries(
                lambda: run_creative_generation(prompt, prompt_append), "Creative Agent"
            )
        except Exception as e:  # noqa: BLE001 — re-raise as a clean service error
            logger.exception("Creative Agent failed")
            raise RuntimeError(f"Creative Agent failed: {e}") from e
        if not creatives:
            raise RuntimeError("Creative Agent returned no creatives.")
        return CreativeGeneration(
            creatives=creatives[:count],
            model_version=settings.gemini_model,
            usage=_usage(raw_usage, started),
        )
