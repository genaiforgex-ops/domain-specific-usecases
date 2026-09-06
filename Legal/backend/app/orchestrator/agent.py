"""Root orchestrator agent and ADK App.

Wires the domain sub-agents under a routing root agent, then wraps them in an
ADK ``App`` (adding long-term-memory compaction when enabled). Tool
implementations and prompt text live elsewhere — this module only assembles.
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.genai import types

from app.adk.models import build_model
from app.config import settings
from app.orchestrator import config as orch_config
from app.orchestrator.prompts import STATIC_HEADER, build_root_instruction
from app.orchestrator.agents.chat import (
    build_compliance_agent,
    build_contract_agent,
    build_discovery_agent,
)
from app.orchestrator.tools import get_current_datetime_tool

logger = logging.getLogger("legalos.orchestrator")


def build_root_agent() -> LlmAgent:
    return LlmAgent(
        model=build_model(),
        name=orch_config.APP_NAME,
        description="LegalOS root assistant — routes legal queries to specialist agents.",
        static_instruction=types.Content(role="user", parts=[types.Part(text=STATIC_HEADER)]),
        instruction=build_root_instruction(),
        generate_content_config=types.GenerateContentConfig(temperature=settings.adk_temperature),
        sub_agents=[
            build_contract_agent(),
            build_compliance_agent(),
            build_discovery_agent(),
        ],
        tools=[get_current_datetime_tool],
    )


def _build_compaction_config():
    """Optional long-term memory: summarize old turns past the interval.

    Guarded — if the installed ADK's compaction API differs we log and skip
    rather than break startup. Short-term memory (full recent history) is
    unaffected.
    """
    if not orch_config.COMPACTION_ENABLED:
        return None
    try:
        from google.adk.apps.app import EventsCompactionConfig
        from google.adk.sessions.summarizers import LlmEventSummarizer

        return EventsCompactionConfig(
            summarizer=LlmEventSummarizer(llm=build_model()),
            compaction_interval=orch_config.COMPACTION_INTERVAL_TURNS,
            overlap_size=orch_config.COMPACTION_OVERLAP_TURNS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Compaction disabled (unsupported by this ADK build): %s", exc)
        return None


def build_app() -> App:
    kwargs = {"name": orch_config.APP_NAME, "root_agent": build_root_agent()}
    compaction = _build_compaction_config()
    if compaction is not None:
        kwargs["events_compaction_config"] = compaction
    return App(**kwargs)
