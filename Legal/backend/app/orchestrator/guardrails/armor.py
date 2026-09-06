"""Input/output armor for the orchestrator.

Input armor (``screen_input``) screens the *masked* user text for prompt
injection / jailbreak / clearly out-of-scope requests and returns a verdict. On
a block, the pipeline never invokes the agent and streams a canned legal
refusal.

Output armor (``sanitize_output``) strips internal agent/tool names and meta
markers from user-facing text (PII restoration is done separately in the
pipeline so it can run once on the assembled final message).

The default screen is a local heuristic (regex + keyword) so no data leaves the
process. When ``settings.orch_dlp_enabled`` is set an LLM-judge / Google Model
Armor path can be layered in here without changing callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Names that must never surface to the user (internal routing vocabulary).
_INTERNAL_NAMES = [
    "legalos_orchestrator",
    "contract_agent",
    "compliance_agent",
    "discovery_agent",
    "transfer_to_agent",
    "get_gmail_thread",
    "get_msa_document",
    "search_jfpsl_knowledge",
    "get_current_datetime",
    "web_search",
]

_META_MARKER = re.compile(r"\[/?(?:INTERPRET|SYSTEM|CONTEXT|THINKING)\]", re.IGNORECASE)

# Heuristic prompt-injection / jailbreak signals.
_INJECTION_PATTERNS = [
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.I),
    re.compile(r"\bdisregard\s+(?:the\s+)?(?:system|previous)\b", re.I),
    re.compile(r"\byou\s+are\s+now\s+(?:a\b|an\b|in\s+developer\s+mode)", re.I),
    re.compile(r"\b(?:dan|jailbreak|do\s+anything\s+now)\b", re.I),
    re.compile(r"\breveal\s+(?:your\s+)?(?:system\s+prompt|instructions?)\b", re.I),
    re.compile(r"\bprint\s+(?:your\s+)?(?:system\s+prompt|hidden\s+instructions?)\b", re.I),
    re.compile(r"\boverride\s+(?:your\s+)?(?:safety|guardrails?)\b", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\bsystem\s+prompt\b", re.I),
]

REFUSAL_MESSAGE = (
    "I can only help with legal matters within LegalOS's scope — contract review, "
    "compliance, MSA/NDA, and legal research for JFPSL. I can't act on that request. "
    "Please rephrase your legal question and I'll be glad to help."
)


@dataclass
class ArmorVerdict:
    blocked: bool
    reason: str | None = None


def screen_input(masked_text: str, *, enabled: bool = True) -> ArmorVerdict:
    """Screen already-PII-masked user text. Returns a block/allow verdict."""
    if not enabled or not masked_text:
        return ArmorVerdict(blocked=False)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(masked_text):
            return ArmorVerdict(blocked=True, reason="prompt_injection")
    return ArmorVerdict(blocked=False)


def sanitize_output(text: str) -> str:
    """Strip internal agent/tool names and meta markers from user-facing text."""
    if not text:
        return text
    cleaned = _META_MARKER.sub("", text)
    for name in _INTERNAL_NAMES:
        cleaned = re.sub(rf"\b{re.escape(name)}\b", "the assistant", cleaned)
    return cleaned
