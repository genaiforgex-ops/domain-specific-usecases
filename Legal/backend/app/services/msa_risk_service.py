"""MSA risk score breakdown and ground-truth status helpers."""

from __future__ import annotations

from app.services.msa_version_service import risk_score_from_suggestions


def ground_truth_status(text: str, guidelines: str | None) -> list[dict]:
    """Return pass/fail status for each ground-truth line."""
    if not guidelines or not guidelines.strip():
        return []
    text_lc = text.lower()
    rows: list[dict] = []
    for raw in guidelines.splitlines():
        expected = raw.strip().strip("-* ")
        if not expected:
            continue
        passed = expected.lower() in text_lc
        rows.append({"term": expected, "passed": passed})
    return rows


def compute_risk_breakdown(
    suggestions: list[dict] | None,
    *,
    guidelines: str | None = None,
    document_text: str | None = None,
    ai_clause_risk: float | None = None,
) -> dict:
    """Build risk breakdown for API responses."""
    items = suggestions or []
    gt_items = [s for s in items if (s.get("order_index") or 0) >= 9000]
    ai_items = [s for s in items if (s.get("order_index") or 0) < 9000]

    by_severity = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for s in items:
        flag = str(s.get("risk_flag") or "none").lower()
        if flag in by_severity:
            by_severity[flag] += 1
        else:
            by_severity["none"] += 1

    gt_status = ground_truth_status(document_text or "", guidelines)
    gt_passed = sum(1 for g in gt_status if g["passed"])
    gt_failed = sum(1 for g in gt_status if not g["passed"])

    overall = risk_score_from_suggestions(items) if items else (ai_clause_risk or 0.0)
    ai_only_score = risk_score_from_suggestions(ai_items) if ai_items else (ai_clause_risk or 0.0)

    return {
        "overall": overall,
        "from_ai_clauses": ai_only_score,
        "from_ground_truth": len(gt_items),
        "by_severity": {
            "high": by_severity["high"],
            "medium": by_severity["medium"],
            "low": by_severity["low"],
        },
        "ground_truth_passed": gt_passed,
        "ground_truth_failed": gt_failed,
        "ground_truth_checks": gt_status,
    }
