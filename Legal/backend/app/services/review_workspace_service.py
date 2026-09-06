"""Shared UC-01 review workspace: playbook context, finding normalization, change history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clause_bank import ClauseBankEntry
from app.models.playbook import PlaybookClause, RegulatorySource
from app.services.ai_service import ClauseAnalysis


@dataclass
class PlaybookContext:
    clauses: list[PlaybookClause]
    regulatory_snippets: list[dict[str, str]]
    clause_bank: list[ClauseBankEntry]


def load_playbook_context(db: Session, contract_type: str) -> PlaybookContext:
    """Load playbook, regulatory excerpts, and clause bank for a contract type."""
    clauses = (
        db.execute(
            select(PlaybookClause).where(
                PlaybookClause.contract_type.in_([contract_type, "ANY"])
            )
        )
        .scalars()
        .all()
    )

    tags: set[str] = {contract_type.upper(), contract_type.lower()}
    for pc in clauses:
        for tag in pc.regulatory_tags or []:
            tags.add(str(tag))

    regulatory_snippets: list[dict[str, str]] = []
    if tags:
        sources = db.execute(select(RegulatorySource)).scalars().all()
        for src in sources:
            src_tags = {str(t).lower() for t in (src.tags or [])}
            if tags & {t.lower() for t in tags} & src_tags or contract_type.lower() in src_tags:
                regulatory_snippets.append(
                    {
                        "reference": src.reference,
                        "title": src.title,
                        "excerpt": (src.content or "")[:1200],
                    }
                )
        regulatory_snippets = regulatory_snippets[:5]

    bank = (
        db.execute(
            select(ClauseBankEntry).where(
                ClauseBankEntry.contract_type.in_([contract_type, "ANY"]),
                ClauseBankEntry.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )

    return PlaybookContext(clauses=clauses, regulatory_snippets=regulatory_snippets, clause_bank=bank)


def _playbook_by_type(playbook: Sequence[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for entry in playbook:
        ct = getattr(entry, "clause_type", None)
        if ct:
            out[str(ct).lower()] = entry
    return out


def _excerpt(text: str, max_len: int = 280) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def enrich_clause_analysis(
    ca: ClauseAnalysis,
    playbook: Sequence[Any],
    clause_bank: Sequence[ClauseBankEntry] | None = None,
) -> ClauseAnalysis:
    """Attach playbook linkage and preferred clause-bank text to a finding."""
    pb_map = _playbook_by_type(playbook)
    clause_type = ca.playbook_clause_type
    if not clause_type:
        for ref in ca.references or []:
            if ref.get("clause_type"):
                clause_type = ref["clause_type"]
                break
        if not clause_type and ca.heading:
            h = ca.heading.lower()
            for key in pb_map:
                if key in h:
                    clause_type = pb_map[key].clause_type
                    break

    entry = pb_map.get((clause_type or "").lower()) if clause_type else None
    if entry is not None:
        ca.playbook_clause_id = getattr(entry, "id", ca.playbook_clause_id)
        ca.playbook_clause_type = entry.clause_type
        if not ca.standard_position_excerpt:
            ca.standard_position_excerpt = _excerpt(entry.standard_position)
        if not ca.proposed_text and entry.fallback_text:
            ca.proposed_text = entry.fallback_text
            ca.suggestion = ca.suggestion or entry.fallback_text
        if getattr(entry, "insert_anchor_hint", None):
            ca.insert_anchor_hint = entry.insert_anchor_hint

    if clause_bank and not ca.clause_bank_id:
        for bank in clause_bank:
            if (
                clause_type
                and bank.clause_type.lower() == clause_type.lower()
                and bank.tier == "preferred"
            ):
                ca.clause_bank_id = bank.id
                if not ca.proposed_text:
                    ca.proposed_text = bank.body_text
                    ca.suggestion = ca.suggestion or bank.body_text
                break

    return ca


def normalize_findings(
    analyses: list[ClauseAnalysis],
    playbook: Sequence[Any],
    clause_bank: Sequence[ClauseBankEntry] | None = None,
) -> list[dict[str, Any]]:
    """Convert ClauseAnalysis list to unified suggestion dicts with playbook linkage."""
    from app.services.suggestion_service import clause_to_suggestion_dict

    return [
        clause_to_suggestion_dict(enrich_clause_analysis(ca, playbook, clause_bank))
        for ca in analyses
    ]


def playbook_summary(contract_type: str, playbook: Sequence[Any]) -> dict[str, Any]:
    """Summary for UI banner."""
    items = [
        p
        for p in playbook
        if getattr(p, "contract_type", contract_type) in (contract_type, "ANY")
    ]
    required = [p for p in items if getattr(p, "is_required", False)]
    return {
        "contract_type": contract_type,
        "clause_count": len(items),
        "required_count": len(required),
    }


def append_change_entry(
    history: list[dict[str, Any]] | None,
    *,
    source: str,
    status: str,
    before: str | None = None,
    after: str | None = None,
    rationale: str | None = None,
    playbook_clause_id: int | None = None,
    decided_by_id: int | None = None,
    order_index: int | None = None,
) -> list[dict[str, Any]]:
    """Append a ReviewChangeEntry to change history JSON."""
    rows = list(history or [])
    rows.append(
        {
            "source": source,
            "status": status,
            "before": before,
            "after": after,
            "rationale": rationale,
            "playbook_clause_id": playbook_clause_id,
            "decided_by_id": decided_by_id,
            "order_index": order_index,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return rows


def format_regulatory_context(snippets: list[dict[str, str]]) -> str:
    if not snippets:
        return ""
    lines = ["REGULATORY CONTEXT (for reference only):"]
    for s in snippets:
        lines.append(f"- [{s['reference']}] {s['title']}: {s['excerpt'][:400]}")
    return "\n".join(lines)
