"""Post-answer citation audit for Research mode.

A citation that points at a real excerpt which does not actually say the thing
claimed is worse than no citation: it looks verified. This module re-reads the
finished answer against the excerpts it cited and demotes any citation the excerpt
does not support, so the user sees "unverified" instead of a false authority.

Flag-gated (`ORCH_RESEARCH_VERIFY_ENABLED`) and fail-open: if the audit itself
errors, the answer is returned untouched rather than blocked.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.orchestrator import config as orch_config

logger = logging.getLogger("legalos.orchestrator")

_CITE_RE = re.compile(r"(?<![\]\w/])\[(\d+)\](?!\()")
_EXCERPT_CHARS = 1500
# Auditing every citation in a long answer costs more than it returns; the first
# dozen cover the substantive claims.
_MAX_CITATIONS = 12


@dataclass
class AuditResult:
    text: str
    unsupported: list[int] = field(default_factory=list)
    checked: int = 0
    ran: bool = False

    @property
    def all_supported(self) -> bool:
        return self.ran and not self.unsupported


def cited_numbers(text: str) -> list[int]:
    """Distinct [n] citation numbers in first-appearance order."""
    seen: dict[int, None] = {}
    for match in _CITE_RE.finditer(text or ""):
        seen.setdefault(int(match.group(1)), None)
    return list(seen)


def build_audit_prompt(text: str, sources: list[dict], citations: list[int]) -> str:
    """The answer plus the excerpt behind each citation, for the auditor."""
    lines = ["ANSWER UNDER AUDIT:", text.strip(), "", "CITED EXCERPTS:"]
    for n in citations:
        src = sources[n - 1] if 0 < n <= len(sources) else None
        if src is None:
            continue
        excerpt = (src.get("chunk_text") or src.get("snippet") or "").strip()
        label = " · ".join(
            p
            for p in (
                str(src.get("title") or "").strip(),
                str(src.get("section_label") or "").strip(),
            )
            if p
        )
        lines.append(f"\n[{n}] {label}\n{excerpt[:_EXCERPT_CHARS]}")
    lines.append(
        "\nFor each citation above, return supported=true only if the excerpt "
        "states or directly entails what the answer attributes to it."
    )
    return "\n".join(lines)


def mark_unsupported(text: str, unsupported: list[int]) -> str:
    """Replace unsupported [n] with an explicit unverified marker."""
    if not unsupported:
        return text
    bad = set(unsupported)

    def _sub(match: re.Match[str]) -> str:
        n = int(match.group(1))
        return "[unverified]" if n in bad else match.group(0)

    out = _CITE_RE.sub(_sub, text)
    note = (
        "\n\n> **Citation check:** "
        + ("one claim" if len(bad) == 1 else f"{len(bad)} claims")
        + " could not be verified against the retrieved sources and "
        + ("is" if len(bad) == 1 else "are")
        + " marked *[unverified]*. Confirm against the primary source before relying on "
        + ("it" if len(bad) == 1 else "them")
        + "."
    )
    return out + note


def audit_answer(
    text: str, sources: list[dict], *, user_id: int | None = None
) -> AuditResult:
    """Blocking audit — call from a worker thread, not the event loop.

    Opens its own short-lived DB session so the verifier's tokens land on
    `llm_usage_logs` with `agent_name="groundedness"`. The chat pipeline has no
    ambient usage context, and a SQLAlchemy session must not be shared across
    threads, so the session is created here rather than passed in.
    """
    if not orch_config.RESEARCH_VERIFY_ENABLED:
        return AuditResult(text=text)
    citations = [n for n in cited_numbers(text) if 0 < n <= len(sources)][:_MAX_CITATIONS]
    if not citations:
        return AuditResult(text=text)

    try:
        from app.adk.runner import run_agent_structured
        from app.database import SessionLocal
        from app.orchestrator.agents import build_groundedness_agent
        from app.orchestrator.metrics import task_usage
        from app.orchestrator.schemas import GroundednessResult

        prompt = build_audit_prompt(text, sources, citations)
        db = SessionLocal()
        try:
            with task_usage(
                db,
                user_id=user_id,
                module="chat",
                operation="verify_groundedness",
                agent_name="groundedness",
            ):
                result = run_agent_structured(
                    build_groundedness_agent(), prompt, GroundednessResult
                )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - fail open: never withhold an answer
        logger.warning("Groundedness audit skipped: %s", exc)
        return AuditResult(text=text)

    unsupported = sorted(
        {v.citation for v in result.verdicts if not v.supported and v.citation in citations}
    )
    if unsupported:
        logger.info("Groundedness audit demoted citations %s", unsupported)
    return AuditResult(
        text=mark_unsupported(text, unsupported),
        unsupported=unsupported,
        checked=len(citations),
        ran=True,
    )


def audit_detail(result: AuditResult) -> str:
    """Markdown for the Thoughts panel."""
    if not result.ran:
        return ""
    if not result.unsupported:
        return f"Checked {result.checked} citation(s) against their excerpts — all supported."
    listed = ", ".join(f"[{n}]" for n in result.unsupported)
    single = len(result.unsupported) == 1
    return (
        f"Checked {result.checked} citation(s). {listed} "
        f"{'was' if single else 'were'} not supported by the cited excerpt and "
        f"{'has' if single else 'have'} been marked *[unverified]* in the answer."
    )
