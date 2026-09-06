"""Validate plain-language edit instructions for Ask AI to Edit."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.orchestrator.guardrails.armor import screen_input

_ACTIONABLE_WORD = re.compile(r"[A-Za-z0-9]{2,}")

# Reject punctuation-only / typo prompts that models otherwise treat as "add a clause".
_MIN_ALNUM = 3

# Jailbreak / role-play / fictional rewrite attempts — not legitimate legal edits.
_UNSAFE_EDIT_PATTERNS = [
    re.compile(r"\b(?:pretend|role[\s-]?play|roleplay)\b", re.I),
    re.compile(r"\bact\s+as\s+(?:if|though|a|an)\b", re.I),
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"\b(?:dan|jailbreak|do\s+anything\s+now)\b", re.I),
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions?\b", re.I),
    re.compile(r"\bdisregard\s+(?:the\s+)?(?:system|previous|safety)\b", re.I),
    re.compile(r"\boverride\s+(?:your\s+)?(?:safety|guardrails?|rules?)\b", re.I),
    re.compile(r"\breveal\s+(?:your\s+)?(?:system\s+prompt|instructions?)\b", re.I),
    re.compile(
        r"\b(?:rewrite|turn|convert|transform)\s+(?:this|it|the\s+(?:document|msa|nda|contract|clause))"
        r"\s+(?:in(?:to)?|as)\s+a?\s*(?:poem|song|joke|story|script|rap|haiku|meme|comedy|fairy\s*tale)\b",
        re.I,
    ),
    re.compile(
        r"\bin\s+the\s+style\s+of\s+(?:a\s+)?(?:pirate|shakespeare|yoda|spongebob|"
        r"disney|dr\.?\s*seuss|comic|stand[\s-]?up)\b",
        re.I,
    ),
    re.compile(r"\b(?:fanfic|fanfiction|make[\s-]?believe|fictional\s+scenario)\b", re.I),
    re.compile(r"\bthis\s+is\s+(?:just\s+)?(?:a\s+)?(?:joke|prank|hypothetical\s+jailbreak)\b", re.I),
    re.compile(r"\b(?:hypothetically|in\s+a\s+fictional\s+world)\b.{0,80}\b(?:ignore|bypass|jailbreak)\b", re.I),
]


ACTIONABLE_EDIT_INSTRUCTION_MESSAGE = (
    "Enter a clear edit instruction (e.g. change X to Y, add a DPDP clause). "
    "Punctuation-only or empty prompts are not allowed."
)

EDIT_REFUSAL_MESSAGE = (
    "I can only apply legitimate legal-document edits for JFPSL counsel "
    "(clause changes, redlines, standard positions). "
    "I can't follow jailbreak, role-play, or fictional rewrite requests. "
    "Please describe a concrete legal edit."
)


@dataclass(frozen=True)
class EditInstructionVerdict:
    allowed: bool
    reason: str | None = None
    message: str | None = None


class EditInstructionRejected(ValueError):
    """Raised when an Ask-AI-to-Edit instruction is blocked."""

    def __init__(self, message: str = EDIT_REFUSAL_MESSAGE, *, reason: str = "blocked") -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason


def is_actionable_edit_instruction(instruction: str | None) -> bool:
    """Return True when the instruction looks like a real edit request.

    ``"."``, ``"..."``, whitespace, and similar non-requests are False.
    """
    text = (instruction or "").strip()
    if not text:
        return False
    alnum = re.sub(r"[^0-9A-Za-z]+", "", text)
    if len(alnum) < _MIN_ALNUM:
        return False
    if not any(ch.isalpha() for ch in alnum):
        return False
    return bool(_ACTIONABLE_WORD.search(text))


def screen_edit_instruction(instruction: str | None) -> EditInstructionVerdict:
    """Allow only concrete legal-edit instructions; block jailbreaks / fiction."""
    text = (instruction or "").strip()
    if not is_actionable_edit_instruction(text):
        return EditInstructionVerdict(
            allowed=False,
            reason="not_actionable",
            message=ACTIONABLE_EDIT_INSTRUCTION_MESSAGE,
        )

    armor = screen_input(text, enabled=True)
    if armor.blocked:
        return EditInstructionVerdict(
            allowed=False,
            reason=armor.reason or "prompt_injection",
            message=EDIT_REFUSAL_MESSAGE,
        )

    for pattern in _UNSAFE_EDIT_PATTERNS:
        if pattern.search(text):
            return EditInstructionVerdict(
                allowed=False,
                reason="unsafe_or_fictional",
                message=EDIT_REFUSAL_MESSAGE,
            )

    return EditInstructionVerdict(allowed=True)


def assert_edit_instruction_allowed(instruction: str | None) -> None:
    verdict = screen_edit_instruction(instruction)
    if not verdict.allowed:
        raise EditInstructionRejected(
            verdict.message or EDIT_REFUSAL_MESSAGE,
            reason=verdict.reason or "blocked",
        )
