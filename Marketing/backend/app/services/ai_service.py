"""AI seam for brief extraction and creative generation.

All AI lives behind this one interface so callers never touch a model SDK. The
only backend is the Google ADK / Gemini agents (Brief Creator + Creative Agent);
there is no deterministic fallback — a failure surfaces as an error rather than
silently returning canned content.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class Usage:
    """Token usage + wall-clock latency for one model call, for cost tracing."""

    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass
class BriefExtraction:
    """Extracted field values keyed by brief column, plus the model + usage."""

    values: dict[str, str] = field(default_factory=dict)
    model_version: str = ""
    usage: Usage = field(default_factory=Usage)


@dataclass
class CreativeGeneration:
    """Generated ad creatives (each a dict of the standard fields), plus model + usage."""

    creatives: list[dict] = field(default_factory=list)
    model_version: str = ""
    usage: Usage = field(default_factory=Usage)


class AIService(ABC):
    @abstractmethod
    def extract_brief(
        self, raw_text: str, brief_type: str, prompt_append: str | None = None
    ) -> BriefExtraction:
        """Map free-form notes into the brief fields for the given type. `prompt_append`
        is the user's Prompt Studio instruction appended to the agent's base prompt."""

    @abstractmethod
    def generate_creatives(
        self, prompt: str, count: int, prompt_append: str | None = None
    ) -> CreativeGeneration:
        """Turn an approved brief + creative prompt into structured ad creatives.
        `prompt_append` is the user's Prompt Studio instruction appended to the base."""


# ── Factory ──────────────────────────────────────────────────────────────────


@lru_cache
def get_ai_service() -> AIService:
    from app.services.adk_ai_service import ADKAIService

    return ADKAIService()
