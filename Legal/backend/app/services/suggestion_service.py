"""Filter, compile, and apply MSA AI clause suggestions onto document text."""

from __future__ import annotations

import difflib
from typing import Any

from app.services.ai_service import ClauseAnalysis

SUGGESTION_CATEGORIES = frozenset(
    {
        "legal_risk",
        "policy",
        "grammar",
        "spelling",
        "ambiguity",
        "missing_clause",
        "definition",
    }
)


def clause_to_suggestion_dict(c: ClauseAnalysis) -> dict[str, Any]:
    """Serialize a ClauseAnalysis into the tracker JSON shape."""
    original = c.original_text if c.original_text is not None else c.clause_text
    proposed = c.proposed_text if c.proposed_text is not None else c.suggestion
    return {
        "order_index": c.order_index,
        "heading": c.heading,
        "clause_text": c.clause_text,
        "risk_flag": c.risk_flag,
        "confidence": c.confidence,
        "rationale": c.rationale,
        "ai_suggestion": c.suggestion,
        "original_text": original,
        "proposed_text": proposed,
        "category": c.category,
        "decision": "pending",
        "playbook_clause_id": c.playbook_clause_id,
        "playbook_clause_type": c.playbook_clause_type,
        "standard_position_excerpt": c.standard_position_excerpt,
        "clause_bank_id": c.clause_bank_id,
        "regulatory_ref": c.regulatory_ref,
        "insert_anchor_hint": c.insert_anchor_hint,
    }


def is_actionable_suggestion(s: dict[str, Any]) -> bool:
    """Return True when a suggestion is worth showing to a reviewer."""
    flag = (s.get("risk_flag") or "none").lower()
    if flag == "none":
        return False

    proposed = _effective_proposed(s, for_preview=False)
    category = (s.get("category") or "legal_risk").lower()

    if category == "missing_clause":
        return bool(proposed and proposed.strip())

    if flag in ("high", "medium"):
        return bool(proposed and proposed.strip())

    if flag == "low":
        return bool(proposed and proposed.strip())

    return False


def filter_actionable_suggestions(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in suggestions if is_actionable_suggestion(s)]


def _effective_proposed(s: dict[str, Any], *, for_preview: bool) -> str | None:
    if for_preview:
        decision = s.get("decision")
        if decision == "modify" and s.get("reviewer_edit"):
            return s["reviewer_edit"]
        if decision == "accept":
            return s.get("proposed_text") or s.get("ai_suggestion")
        return None
    return s.get("proposed_text") or s.get("ai_suggestion")


def _replacement_for(s: dict[str, Any]) -> str | None:
    decision = s.get("decision")
    if decision == "reject" or decision == "pending":
        return None
    if decision == "modify" and s.get("reviewer_edit"):
        return s["reviewer_edit"]
    if decision == "accept":
        return s.get("proposed_text") or s.get("ai_suggestion")
    return None


def _find_insert_position(
    text: str,
    anchor_hint: str | None,
    clause_type: str | None,
) -> int | None:
    """Return character index to insert after anchor, or None for append."""
    for needle in (anchor_hint, clause_type):
        if not needle:
            continue
        pos = text.lower().find(needle.lower())
        if pos >= 0:
            nl = text.find("\n", pos)
            return nl + 1 if nl >= 0 else len(text)
    return None


def compile_accepted_suggestions(
    base_text: str,
    suggestions: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply accepted/modified suggestions to base_text.

    Returns (edited_text, applied, blocked).
    """
    to_apply = [s for s in suggestions if _replacement_for(s)]
    applied: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    text = base_text

    # Apply insertions (missing clauses) first, then replacements from end to start.
    insertions = [s for s in to_apply if (s.get("category") or "").lower() == "missing_clause"]
    replacements = [s for s in to_apply if (s.get("category") or "").lower() != "missing_clause"]

    for s in insertions:
        replacement = _replacement_for(s)
        if not replacement:
            continue
        heading = s.get("heading") or "Additional clause"
        block = f"\n\n{heading}\n{replacement}"
        pos = _find_insert_position(
            text,
            s.get("insert_anchor_hint"),
            s.get("playbook_clause_type"),
        )
        if pos is not None:
            text = text[:pos] + block + text[pos:]
            applied.append({**s, "apply_note": "inserted after anchor"})
        else:
            text = text.rstrip() + block
            applied.append({**s, "apply_note": "inserted at end (anchor not found)"})

    # Sort replacements by last occurrence position (desc) to reduce offset drift.
    ordered: list[tuple[int, dict[str, Any], str, str]] = []
    for s in replacements:
        replacement = _replacement_for(s)
        if not replacement:
            continue
        original = (s.get("original_text") or s.get("clause_text") or "").strip()
        if not original:
            blocked.append({**s, "apply_error": "No original excerpt to replace"})
            continue
        pos = text.rfind(original)
        if pos < 0:
            blocked.append({**s, "apply_error": "Original excerpt not found in document"})
            continue
        ordered.append((pos, s, original, replacement))

    ordered.sort(key=lambda x: x[0], reverse=True)
    used_ranges: list[tuple[int, int]] = []

    for pos, s, original, replacement in ordered:
        end = pos + len(original)
        if any(not (end <= start or pos >= stop) for start, stop in used_ranges):
            blocked.append({**s, "apply_error": "Overlapping change — resolve manually"})
            continue
        if text[pos:end] != original:
            blocked.append({**s, "apply_error": "Ambiguous match at apply time"})
            continue
        text = text[:pos] + replacement + text[end:]
        used_ranges.append((pos, end))
        applied.append({**s, "apply_note": "replaced excerpt"})

    return text, applied, blocked


def replacement_pairs(applied: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Build (original, replacement) pairs from applied suggestion dicts."""
    pairs: list[tuple[str, str]] = []
    for s in applied:
        repl = _replacement_for(s)
        if not repl:
            continue
        original = (s.get("original_text") or s.get("clause_text") or "").strip()
        if original:
            pairs.append((original, repl))
    return pairs


def line_diff(before: str, after: str) -> list[dict[str, str]]:
    a_lines = before.splitlines()
    b_lines = after.splitlines()
    blocks: list[dict[str, str]] = []
    # autojunk=False keeps long documents accurate — the default "popular line"
    # heuristic can otherwise mis-align large sections (e.g. the document tail
    # showing up as inserted on every edit).
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=a_lines, b=b_lines, autojunk=False
    ).get_opcodes():
        blocks.append(
            {
                "kind": tag,
                "v1": "\n".join(a_lines[i1:i2]),
                "v2": "\n".join(b_lines[j1:j2]),
            }
        )
    return blocks
