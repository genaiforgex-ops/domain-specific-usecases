"""Deterministic stub helpers and shared result dataclasses for LegalAI.

LLM generation lives under ``app.orchestrator.tasks``. ``StubLegalAIService``
provides corpus-bounded fallbacks when ``AI_BACKEND=stub`` or an agent call fails.

BRD constraint (§7 Principle 4 + §11.3): all AI inference for legal data MUST
remain within JFPSL infra. No external LLM API for legal documents.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class ClauseAnalysis:
    order_index: int
    heading: str | None
    clause_text: str
    risk_flag: str  # high | medium | low | none
    confidence: float
    rationale: str
    suggestion: str | None
    references: list[dict[str, Any]] = field(default_factory=list)
    original_text: str | None = None
    proposed_text: str | None = None
    category: str = "legal_risk"
    playbook_clause_id: int | None = None
    playbook_clause_type: str | None = None
    standard_position_excerpt: str | None = None
    clause_bank_id: int | None = None
    regulatory_ref: str | None = None
    insert_anchor_hint: str | None = None


@dataclass
class ContractAnalysisResult:
    clauses: list[ClauseAnalysis]
    risk_score: float
    model_version: str


@dataclass
class DiffToken:
    text: str
    op: str  # equal | insert | delete


@dataclass
class DiffBlock:
    kind: str
    v1: str
    v2: str
    # Word-level breakdown, populated for "replace" blocks so the UI can highlight
    # exactly which tokens changed instead of lighting up the whole line.
    v1_tokens: list[DiffToken] | None = None
    v2_tokens: list[DiffToken] | None = None


@dataclass
class RiskFlag:
    severity: str
    excerpt: str
    rationale: str


@dataclass
class ComparisonResult:
    diff_blocks: list[DiffBlock]
    risk_commentary: list[RiskFlag]
    summary_report: str
    model_version: str


@dataclass
class NegotiationChangeItem:
    diff_index: int
    title: str
    old_text: str
    new_text: str
    severity: str
    impact: str
    suggested_action: str
    # Where in the document: nearest section/clause heading (e.g. "§7. Limitation of Liability").
    clause_ref: str = ""
    # Precise what-changed line derived from the word-level diff
    # (e.g. 'Changed "30 days" → "60 days"').
    change_summary: str = ""
    # Why this was flagged / the reasoning behind the suggested action.
    rationale: str = ""


@dataclass
class NegotiationChangeSummary:
    changes: list[NegotiationChangeItem]
    executive_summary: str
    model_version: str


@dataclass
class LegalBotResult:
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    tier: int
    model_version: str


@dataclass
class ResearchResult:
    summary: str
    applicable_regulations: list[dict[str, Any]]
    key_provisions: list[dict[str, Any]]
    implications: str
    recommended_next_steps: list[str]
    citations: list[dict[str, Any]]
    confidence: float
    model_version: str


@dataclass
class NewsAnalysis:
    summary: str
    tags: list[str]
    relevance_score: float
    model_version: str
    category: str = "Other"
    impact_note: str | None = None


@dataclass
class EditChange:
    description: str
    original: str
    revised: str


@dataclass
class DocumentEditResult:
    """Result of a prompt-based document edit (proposed, never auto-applied)."""

    edited_text: str
    change_summary: str
    changes: list[EditChange]
    model_version: str


@dataclass
class DocxOperationItem:
    op_type: str
    anchor_id: str | None
    after_anchor_id: str | None
    target_text: str | None
    content: str | None
    description: str
    confidence: float


@dataclass
class DocxEditPlanResult:
    """Structured DOCX edit plan (operations, not full-text rewrite)."""

    change_summary: str
    operations: list[DocxOperationItem]
    model_version: str
    used_fallback: bool = False


@dataclass
class ExtractedTask:
    title: str
    description: str
    priority: str  # P0..P3
    priority_score: float
    confidence: float
    rationale: str
    due_date: Any  # datetime | None — kept as Any to avoid import here
    tags: list[str]
    estimated_minutes: int | None
    model_version: str


@dataclass
class EmailReplyResult:
    subject: str
    body: str
    confidence: float
    rationale: str
    model_version: str


# ── Interface ─────────────────────────────────────────────────────────────────


class LegalAIService(ABC):
    """Implement this interface to plug in any LLM backend."""

    model_version: str

    @abstractmethod
    def review_contract(
        self,
        raw_text: str,
        playbook: Sequence[Any],
        contract_type: str = "MSA",
    ) -> ContractAnalysisResult: ...

    @abstractmethod
    def compare_documents(self, v1_text: str, v2_text: str) -> ComparisonResult: ...

    @abstractmethod
    def summarize_document_changes(
        self,
        v1_text: str,
        v2_text: str,
        diff_blocks: list[DiffBlock],
        risk_commentary: list[RiskFlag],
        contract_type: str = "MSA",
    ) -> NegotiationChangeSummary: ...

    @abstractmethod
    def answer_legal_bot(
        self,
        question: str,
        knowledge_base: Sequence[Any],
    ) -> LegalBotResult: ...

    def answer_legal_bot_with_document(
        self,
        question: str,
        knowledge_base: Sequence[Any],
        document_text: str,
        memory_snippets: list[str] | None = None,
    ) -> LegalBotResult:
        """Answer using knowledge base plus a specific contract document excerpt."""
        return self._answer_legal_bot_with_document_impl(
            question, knowledge_base, document_text, memory_snippets
        )

    def _answer_legal_bot_with_document_impl(
        self,
        question: str,
        knowledge_base: Sequence[Any],
        document_text: str,
        memory_snippets: list[str] | None,
    ) -> LegalBotResult:
        kb_result = self.answer_legal_bot(question, knowledge_base)
        q_terms = [t for t in re.split(r"\W+", question.lower()) if len(t) > 3]
        excerpts: list[str] = []
        for para in document_text.split("\n"):
            pl = para.strip()
            if not pl:
                continue
            pl_lc = pl.lower()
            if any(t in pl_lc for t in q_terms):
                excerpts.append(pl[:500])
            if len(excerpts) >= 4:
                break
        doc_citations = [{"source": "document", "excerpt": e} for e in excerpts]
        if not excerpts:
            if len(document_text.strip()) < 50:
                return kb_result
            return LegalBotResult(
                answer=(
                    f"{kb_result.answer}\n\n"
                    "I could not locate a specific clause excerpt for this question in the "
                    "attached document version. Please review the full text or escalate to Legal."
                ),
                citations=list(kb_result.citations or []),
                confidence=max(0.2, kb_result.confidence - 0.15),
                tier=2 if kb_result.tier == 2 else 2,
                model_version=kb_result.model_version,
            )
        excerpt_block = "\n".join(f"- {e[:280]}" for e in excerpts[:3])
        mem_block = ""
        if memory_snippets:
            mem_block = "\n\nNegotiation context:\n" + "\n".join(memory_snippets[:4])
        answer = (
            f"{kb_result.answer}\n\n"
            f"From this document version:\n{excerpt_block}"
            f"{mem_block}\n\n"
            "This is an AI explanation for guidance only — not legal advice."
        )
        citations = list(kb_result.citations or []) + doc_citations
        confidence = min(0.95, kb_result.confidence + (0.12 if excerpts else 0))
        tier = 1 if confidence >= 0.55 and kb_result.tier == 1 else kb_result.tier
        return LegalBotResult(
            answer=answer.strip(),
            citations=citations,
            confidence=round(confidence, 2),
            tier=tier,
            model_version=kb_result.model_version,
        )

    @abstractmethod
    def generate_research_note(
        self,
        query: str,
        regulatory_corpus: Sequence[Any],
    ) -> ResearchResult: ...

    @abstractmethod
    def analyse_regulatory_update(
        self,
        source: str,
        title: str,
        full_text: str,
    ) -> NewsAnalysis: ...

    @abstractmethod
    def extract_tasks_from_email(
        self,
        sender_name: str,
        sender_email: str,
        subject: str,
        body: str,
        thread_summary: str = "",
        allow_fallback: bool = True,
    ) -> list[ExtractedTask]: ...

    @abstractmethod
    def generate_email_reply(
        self,
        latest_body: str,
        original_subject: str,
        from_addr: str,
        prior_summary: str = "",
        user_feedback: str | None = None,
    ) -> EmailReplyResult: ...

    @abstractmethod
    def score_task_priority(
        self,
        title: str,
        description: str | None,
        sender_email: str | None,
        due_date: Any,
    ) -> tuple[str, float, str]:
        """Return (priority_label, score, rationale)."""

    @abstractmethod
    def edit_document(
        self,
        base_text: str,
        instruction: str,
        selection: str | None = None,
    ) -> DocumentEditResult:
        """Apply a lawyer's plain-language edit instruction to a document.

        Returns the proposed full edited text plus an itemised redline. The
        result is always a *proposal* — callers must surface it for review and
        never auto-finalize (UC-01 §2.8 reviewer-control guardrail).
        """

    @abstractmethod
    def plan_docx_operations(
        self,
        structure: dict[str, Any],
        instruction: str,
        selection: str | None = None,
        edit_memory: list[str] | None = None,
        full_text: str | None = None,
    ) -> DocxEditPlanResult:
        """Plan high-fidelity DOCX edits as structured operations against document parts."""


# ── Deterministic stub ────────────────────────────────────────────────────────

_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*[.\)]?\s*(.{0,80})", re.MULTILINE)
_MATERIAL_KEYWORDS = (
    "liability",
    "indemnif",
    "payment",
    "termination",
    "confidential",
    "jurisdiction",
    "governing law",
    "warranty",
    "arbitration",
    "intellectual property",
    "data protection",
)
_TIER1_THRESHOLD = 0.55

# Ordered by priority — first substring match wins. Each entry is
# (keyword, severity, why-it-matters rationale grounded in the JFPSL playbook).
_TERM_GUIDANCE: list[tuple[str, str, str]] = [
    ("liability", "high", "Affects JFPSL's financial exposure and the liability cap."),
    ("indemnif", "high", "Indemnity allocation shifts legal risk between the parties."),
    ("terminat", "high", "Changes exit rights / notice period — review continuity and lock-in."),
    ("intellectual property", "high", "IP ownership or licence terms — protect JFPSL's rights."),
    ("data protection", "high", "Data-protection obligations carry DPDP regulatory exposure."),
    ("governing law", "high", "Governing-law change affects enforceability of the contract."),
    ("jurisdiction", "high", "Jurisdiction change affects where disputes are heard."),
    ("confidential", "medium", "Confidentiality scope affects information-sharing risk."),
    ("payment", "medium", "Payment terms affect cash-flow and agreed commercials."),
    ("fee", "medium", "Fee / pricing change — verify against the agreed commercials."),
    ("warranty", "medium", "Warranty scope affects the remedies available to JFPSL."),
    ("arbitration", "medium", "Dispute-resolution mechanism changed — review seat and rules."),
]

# Section / clause heading patterns used to locate where a change sits.
_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?:section|clause|article)\s+[0-9ivxlc]+\b.*"  # "Section 7 ...", "Article IV ..."
    r"|[0-9]+(?:\.[0-9]+)*[.)]?\s+[A-Z].{0,70}"      # "7. Limitation of Liability", "7.2 Notices"
    r")$",
    re.IGNORECASE,
)


def _condense(text: str, limit: int = 90) -> str:
    """Collapse whitespace and clip a chunk to a short, readable snippet."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _change_summary(block: "DiffBlock") -> str:
    """One-line, precise description of what changed, from the word-level diff.

    Falls back to a condensed chunk when token-level data is unavailable
    (e.g. pure insert/delete blocks or older stored comparisons).
    """
    if block.kind == "insert":
        s = _condense(block.v2)
        return f'Added: "{s}"' if s else "New content added."
    if block.kind == "delete":
        s = _condense(block.v1)
        return f'Removed: "{s}"' if s else "Content removed."
    # replace — prefer the exact tokens that changed
    removed = [t.text.strip() for t in (block.v1_tokens or []) if t.op == "delete" and t.text.strip()]
    added = [t.text.strip() for t in (block.v2_tokens or []) if t.op == "insert" and t.text.strip()]
    if removed or added:
        rem = "; ".join(f'"{_condense(x, 40)}"' for x in removed[:4])
        add = "; ".join(f'"{_condense(x, 40)}"' for x in added[:4])
        if removed and added:
            return f"Changed {rem} → {add}"
        if added:
            return f"Inserted {add}"
        return f"Deleted {rem}"
    return f'Reworded: "{_condense(block.v1, 45)}" → "{_condense(block.v2, 45)}"'


def _nearest_heading(diff_blocks: list["DiffBlock"], index: int) -> str:
    """Walk backwards from the changed block to the closest section/clause heading."""

    def scan(text: str) -> str:
        for line in reversed((text or "").splitlines()):
            if _HEADING_RE.match(line.strip()):
                return _condense(line, 70)
        return ""

    # The changed block itself may open with a heading; otherwise look upstream.
    own = diff_blocks[index]
    hit = scan(own.v2) or scan(own.v1)
    if hit:
        return hit
    for j in range(index - 1, -1, -1):
        b = diff_blocks[j]
        hit = scan(b.v2 if b.v2 else b.v1)
        if hit:
            return hit
    return ""


def _classify_change(combined: str) -> tuple[str, str, str]:
    """Return (severity, matched_keyword, rationale) for a changed chunk."""
    for kw, severity, why in _TERM_GUIDANCE:
        if kw in combined:
            return severity, kw, why
    return "low", "", "Drafting or minor change — confirm it is acceptable."

_SPELLING_FIXES: list[tuple[str, str, str]] = [
    (r"\bgrammer\b", "grammar", "Correct spelling: grammar"),
    (r"\brecieve\b", "receive", "Correct spelling: receive"),
    (r"\boccured\b", "occurred", "Correct spelling: occurred"),
    (r"\bseperate\b", "separate", "Correct spelling: separate"),
    (r"\bdefinately\b", "definitely", "Correct spelling: definitely"),
]

_RED_FLAG_REPLACEMENTS: list[tuple[str, str, str, str]] = [
    (
        "unlimited liability",
        "high",
        "liability limited to fees paid in the twelve (12) months preceding the claim, on a mutual basis",
        "Cap unlimited liability and make mutual",
    ),
    (
        "sole discretion",
        "medium",
        "mutual agreement of the parties",
        "Replace sole discretion with mutual agreement",
    ),
    (
        "no liability",
        "high",
        "liability limited to fees paid in the twelve (12) months preceding the claim",
        "Replace blanket no-liability with a capped liability",
    ),
    (
        "any and all damages",
        "high",
        "direct damages only, subject to the liability cap in this Agreement",
        "Limit damages to direct damages under the liability cap",
    ),
]


def _split_clauses(text: str) -> list[tuple[str | None, str]]:
    """Split a contract into (heading, body) tuples by numbered markers / paragraphs."""
    text = text.strip()
    matches = list(_NUMBERED_HEADING.finditer(text))
    if not matches:
        # fallback: split by double newlines
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [(None, p) for p in paragraphs]
    clauses: list[tuple[str | None, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        first_line = block.split("\n", 1)[0]
        heading = first_line[:120]
        clauses.append((heading, block))
    return clauses


def _deterministic_confidence(seed: str, lo: float = 0.6, hi: float = 0.95) -> float:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return round(lo + (h % 1000) / 1000 * (hi - lo), 2)


_STANDARD_DPDP_CLAUSE = (
    "Data Protection. Each party shall comply with applicable data-protection laws, "
    "including the Digital Personal Data Protection Act, 2023. Personal data shall be "
    "processed only on documented instructions, with appropriate technical and "
    "organisational safeguards, breach notification within 72 hours, and deletion or "
    "return upon termination."
)

_LIABILITY_REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        r"unlimited\s+liability",
        "liability limited to fees paid in the twelve (12) months preceding the claim, on a mutual basis",
        "Capped unlimited liability and made mutual",
    ),
    (
        r"(?i)vendor['']s\s+total\s+(?:aggregate\s+)?liability",
        "Each party's total aggregate liability",
        "Made liability cap mutual",
    ),
    (
        r"(?i)customer['']s\s+total\s+(?:aggregate\s+)?liability\s+shall\s+not\s+exceed",
        "Each party's total aggregate liability shall not exceed",
        "Extended liability cap to both parties",
    ),
]


def _replace_first(text: str, pattern: str, replacement: str, flags: int = re.IGNORECASE) -> tuple[str, str | None]:
    m = re.search(pattern, text, flags)
    if not m:
        return text, None
    original = m.group(0)
    return text[: m.start()] + replacement + text[m.end() :], original


def _stub_edit_document(
    base_text: str,
    instruction: str,
    selection: str | None,
    model_version: str,
) -> DocumentEditResult:
    from app.services.edit_instruction import (
        EDIT_REFUSAL_MESSAGE,
        is_actionable_edit_instruction,
        screen_edit_instruction,
    )

    instruction = instruction.strip()
    instruction_lc = instruction.lower()
    sel = (selection or "").strip()
    scope = sel if sel else base_text

    verdict = screen_edit_instruction(instruction)
    if not verdict.allowed:
        return DocumentEditResult(
            edited_text=base_text,
            change_summary=verdict.message or EDIT_REFUSAL_MESSAGE,
            changes=[],
            model_version=model_version,
        )

    if not is_actionable_edit_instruction(instruction):
        return DocumentEditResult(
            edited_text=base_text,
            change_summary=(
                "No edit applied — instruction is too vague or empty. "
                "Describe a concrete change (e.g. change X to Y, add a DPDP clause)."
            ),
            changes=[],
            model_version=model_version,
        )

    edited_scope = scope
    changes: list[EditChange] = []
    summary_parts: list[str] = []

    replace_match = re.search(
        r"(?:change|replace)\s+[\"']?(.+?)[\"']?\s+(?:to|with)\s+[\"']?(.+?)[\"']?\s*$",
        instruction,
        re.IGNORECASE | re.DOTALL,
    )
    if replace_match:
        old, new = replace_match.group(1).strip(), replace_match.group(2).strip()
        if old in scope:
            edited_scope = scope.replace(old, new, 1)
            changes.append(EditChange(description=instruction, original=old, revised=new))
            summary_parts.append(f"Replaced \"{old[:60]}\" with \"{new[:60]}\".")
        else:
            idx = scope.lower().find(old.lower())
            if idx >= 0:
                original = scope[idx : idx + len(old)]
                edited_scope = scope[:idx] + new + scope[idx + len(old) :]
                changes.append(EditChange(description=instruction, original=original, revised=new))
                summary_parts.append(f"Replaced \"{original[:60]}\" with \"{new[:60]}\".")

    elif "dpdp" in instruction_lc or "data protection" in instruction_lc or "data-protection" in instruction_lc:
        if sel:
            edited_scope = scope.rstrip() + "\n\n" + _STANDARD_DPDP_CLAUSE
            changes.append(EditChange(description="Insert DPDP clause", original="", revised=_STANDARD_DPDP_CLAUSE))
        else:
            edited_scope = base_text.rstrip() + "\n\n" + _STANDARD_DPDP_CLAUSE
            changes.append(EditChange(description="Insert DPDP clause", original="", revised=_STANDARD_DPDP_CLAUSE))
        summary_parts.append("Added a standard DPDP / data-protection clause.")

    elif "liabilit" in instruction_lc and any(
        w in instruction_lc for w in ("mutual", "12 month", "twelve month", "cap", "limit")
    ):
        for pattern, replacement, desc in _LIABILITY_REPLACEMENTS:
            updated, original = _replace_first(edited_scope, pattern, replacement)
            if original:
                edited_scope = updated
                changes.append(EditChange(description=desc, original=original, revised=replacement))
                summary_parts.append(desc + ".")
        if not changes and "12" in instruction_lc:
            cap = (
                "Each party's total aggregate liability shall not exceed the fees paid "
                "by Customer to Vendor in the twelve (12) months immediately preceding the claim."
            )
            edited_scope = scope.rstrip() + "\n\n" + cap
            changes.append(EditChange(description="Insert mutual liability cap", original="", revised=cap))
            summary_parts.append("Inserted a 12-month mutual liability cap.")

    elif any(w in instruction_lc for w in ("remove", "delete", "strike", "drop")) and sel:
        edited_scope = ""
        changes.append(EditChange(description=instruction, original=sel, revised=""))
        summary_parts.append("Removed the selected passage.")

    elif any(w in instruction_lc for w in ("add", "insert", "include")) and "clause" in instruction_lc:
        addition = f"[Added per instruction: {instruction}]"
        edited_scope = scope.rstrip() + "\n\n" + addition
        changes.append(EditChange(description=instruction, original="", revised=addition))
        summary_parts.append("Inserted new clause text reflecting your instruction.")

    elif sel and any(w in instruction_lc for w in ("amend", "revise", "update", "rewrite", "clarify")):
        amended = scope.rstrip() + f"\n\n[Amended: {instruction}]"
        edited_scope = amended
        changes.append(EditChange(description=instruction, original=scope, revised=amended))
        summary_parts.append("Applied your instruction to the selected text.")

    else:
        # Unrecognized but non-empty instruction — do not invent clauses.
        edited_scope = scope
        summary_parts.append(
            "No concrete edit was applied; refine the instruction "
            '(e.g. "change X to Y", "add a DPDP clause", or select text to delete).'
        )

    if not changes:
        edited_full = base_text
    elif sel:
        if sel in base_text:
            edited_full = base_text.replace(sel, edited_scope, 1)
        else:
            idx = base_text.find(scope)
            edited_full = (
                base_text.replace(scope, edited_scope, 1) if idx >= 0 else base_text
            )
    else:
        edited_full = edited_scope

    if not summary_parts:
        summary_parts.append("No document changes proposed.")

    return DocumentEditResult(
        edited_text=edited_full,
        change_summary=" ".join(summary_parts),
        changes=changes,
        model_version=model_version,
    )


def _find_anchor_for_text(structure: dict[str, Any], text: str) -> str | None:
    needle = (text or "").strip()
    if not needle:
        return None
    for part in structure.get("parts", []):
        part_text = part.get("text") or ""
        if needle in part_text:
            return part.get("id")
    return None


def _stub_plan_docx_operations(
    structure: dict[str, Any],
    instruction: str,
    selection: str | None,
    edit_memory: list[str] | None,
    model_version: str,
    full_text: str | None = None,
) -> DocxEditPlanResult:
    from app.services.docx_structure_service import last_body_part_id_from_dict
    from app.services.edit_instruction import EDIT_REFUSAL_MESSAGE, screen_edit_instruction

    verdict = screen_edit_instruction(instruction)
    if not verdict.allowed:
        return DocxEditPlanResult(
            change_summary=verdict.message or EDIT_REFUSAL_MESSAGE,
            operations=[],
            model_version=model_version,
        )

    base_text = (full_text or structure.get("full_text") or "").strip()
    effective_instruction = instruction
    if edit_memory:
        memory_block = "\n".join(f"- {m}" for m in edit_memory)
        effective_instruction = f"{instruction}\n\nPrior applied edits:\n{memory_block}"

    edit_result = _stub_edit_document(base_text, effective_instruction, selection, model_version)
    operations: list[DocxOperationItem] = []

    for change in edit_result.changes:
        original = (change.original or "").strip()
        revised = (change.revised or "").strip()
        if original and revised:
            anchor_id = _find_anchor_for_text(structure, original)
            operations.append(
                DocxOperationItem(
                    op_type="replace_span" if anchor_id else "replace_clause",
                    anchor_id=anchor_id,
                    after_anchor_id=None,
                    target_text=original,
                    content=revised,
                    description=change.description,
                    confidence=0.75 if anchor_id else 0.5,
                )
            )
        elif original and not revised:
            anchor_id = _find_anchor_for_text(structure, original)
            operations.append(
                DocxOperationItem(
                    op_type="delete_clause",
                    anchor_id=anchor_id,
                    after_anchor_id=None,
                    target_text=original,
                    content=None,
                    description=change.description,
                    confidence=0.7 if anchor_id else 0.5,
                )
            )
        elif revised:
            after_id = last_body_part_id_from_dict(structure)
            op_type = "add_definition" if "definition" in instruction.lower() else "insert_clause"
            operations.append(
                DocxOperationItem(
                    op_type=op_type,
                    anchor_id=None,
                    after_anchor_id=after_id,
                    target_text=None,
                    content=revised,
                    description=change.description,
                    confidence=0.7,
                )
            )

    if not operations:
        return DocxEditPlanResult(
            change_summary=edit_result.change_summary
            or "No concrete edit was applied; refine the instruction.",
            operations=[],
            model_version=model_version,
        )

    return DocxEditPlanResult(
        change_summary=edit_result.change_summary,
        operations=operations,
        model_version=model_version,
    )


class StubLegalAIService(LegalAIService):
    """Deterministic, corpus-bounded stub. Production swaps this for a real LLM.

    Hallucination guard: only references documents passed in via the playbook /
    knowledge_base / regulatory_corpus arguments. Will not invent citations.
    """

    def __init__(self, model_version: str = "legalos-stub-0.1") -> None:
        self.model_version = model_version

    # UC-01 Contract Review
    def review_contract(
        self,
        raw_text: str,
        playbook: Sequence[Any],
        contract_type: str = "MSA",
    ) -> ContractAnalysisResult:
        clauses = _split_clauses(raw_text)
        raw_lc = raw_text.lower()
        pb_index: list[tuple[str, list[str], str, Any]] = []
        for entry in playbook:
            if getattr(entry, "contract_type", contract_type) not in (contract_type, "ANY"):
                continue
            keywords = [k.lower() for k in (getattr(entry, "risk_keywords", []) or [])]
            pb_index.append((entry.clause_type, keywords, entry.standard_position, entry))

        analyses: list[ClauseAnalysis] = []
        total_severity = 0.0
        order = 0
        matched_playbook_types: set[str] = set()

        for heading, body in clauses:
            body_lc = body.lower()
            matched_type: str | None = None
            matched_entry: Any = None
            matched_position: str | None = None
            for clause_type, keywords, position, entry in pb_index:
                hits = [kw for kw in keywords if kw and kw in body_lc]
                if hits or clause_type.lower() in (heading or "").lower():
                    matched_type = clause_type
                    matched_entry = entry
                    matched_position = position
                    matched_playbook_types.add(clause_type.lower())
                    break

            findings_for_clause: list[ClauseAnalysis] = []

            if matched_entry and matched_type and matched_position:
                pos_lc = matched_position.lower()
                if ("twelve" in pos_lc or "12 months" in pos_lc) and "unlimited" in body_lc:
                    fallback = getattr(matched_entry, "fallback_text", None) or matched_position
                    findings_for_clause.append(
                        ClauseAnalysis(
                            order_index=order,
                            heading=heading,
                            clause_text=body,
                            risk_flag="high",
                            confidence=0.88,
                            rationale=(
                                f"Draft deviates from JFPSL standard position for {matched_type}."
                            ),
                            suggestion=fallback,
                            references=[{"source": "playbook", "clause_type": matched_type}],
                            original_text=body[:200] if len(body) > 200 else body,
                            proposed_text=fallback,
                            category="legal_risk",
                            playbook_clause_id=getattr(matched_entry, "id", None),
                            playbook_clause_type=matched_type,
                            standard_position_excerpt=matched_position[:280],
                        )
                    )
                    order += 1
                    total_severity += 0.9

            for phrase, level, replacement, desc in _RED_FLAG_REPLACEMENTS:
                if phrase in body_lc:
                    idx = body_lc.find(phrase)
                    original = body[idx : idx + len(phrase)]
                    findings_for_clause.append(
                        ClauseAnalysis(
                            order_index=order,
                            heading=heading,
                            clause_text=body,
                            risk_flag=level,
                            confidence=_deterministic_confidence(f"{phrase}|{body[:120]}"),
                            rationale=f'{desc}: contains red-flag phrase "{phrase}".',
                            suggestion=replacement,
                            references=[{"source": "playbook", "clause_type": matched_type or "risk"}],
                            original_text=original,
                            proposed_text=replacement,
                            category="legal_risk",
                        )
                    )
                    order += 1
                    total_severity += 0.9 if level == "high" else 0.6

            for pattern, fix, desc in _SPELLING_FIXES:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    original = m.group(0)
                    findings_for_clause.append(
                        ClauseAnalysis(
                            order_index=order,
                            heading=heading,
                            clause_text=body,
                            risk_flag="low",
                            confidence=0.85,
                            rationale=desc,
                            suggestion=fix,
                            references=[],
                            original_text=original,
                            proposed_text=fix,
                            category="spelling",
                        )
                    )
                    order += 1
                    total_severity += 0.15

            analyses.extend(findings_for_clause)

        # Required playbook clauses missing from draft
        for clause_type, keywords, position, entry in pb_index:
            if not getattr(entry, "is_required", False):
                # Heuristic: Data Protection and Governing Law treated as required for ANY
                if clause_type not in ("Data Protection", "Governing Law"):
                    continue
            if clause_type.lower() in matched_playbook_types:
                continue
            found = any(kw and kw in raw_lc for kw in keywords)
            if found:
                matched_playbook_types.add(clause_type.lower())
                continue
            fallback = getattr(entry, "fallback_text", None) or position
            analyses.append(
                ClauseAnalysis(
                    order_index=order,
                    heading=f"MISSING: {clause_type}",
                    clause_text="(Required by our standard position but absent from the draft.)",
                    risk_flag="high",
                    confidence=0.85,
                    rationale=(
                        f"Required playbook clause '{clause_type}' was not found in the counterparty draft."
                    ),
                    suggestion=fallback,
                    references=[{"source": "playbook", "clause_type": clause_type}],
                    original_text=None,
                    proposed_text=fallback,
                    category="missing_clause",
                    playbook_clause_id=getattr(entry, "id", None),
                    playbook_clause_type=clause_type,
                    standard_position_excerpt=(position or "")[:280],
                )
            )
            order += 1
            total_severity += 0.9

        n = max(1, len(analyses) or 1)
        # Score 0..100, higher = riskier
        risk_score = round(min(100.0, (total_severity / n) * 100), 1)
        return ContractAnalysisResult(clauses=analyses, risk_score=risk_score, model_version=self.model_version)

    @staticmethod
    def _word_diff(a: str, b: str) -> tuple[list[DiffToken], list[DiffToken]]:
        """Token-level diff of two text chunks.

        Returns (v1_tokens, v2_tokens). Whitespace is preserved as its own tokens so
        the original text can be reconstructed verbatim by concatenating token text.
        v1 carries equal/delete tokens; v2 carries equal/insert tokens.
        """
        a_toks = re.findall(r"\S+|\s+", a)
        b_toks = re.findall(r"\S+|\s+", b)
        sm = difflib.SequenceMatcher(a=a_toks, b=b_toks, autojunk=False)
        v1_out: list[DiffToken] = []
        v2_out: list[DiffToken] = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                v1_out.append(DiffToken("".join(a_toks[i1:i2]), "equal"))
                v2_out.append(DiffToken("".join(b_toks[j1:j2]), "equal"))
            elif tag == "delete":
                v1_out.append(DiffToken("".join(a_toks[i1:i2]), "delete"))
            elif tag == "insert":
                v2_out.append(DiffToken("".join(b_toks[j1:j2]), "insert"))
            elif tag == "replace":
                v1_out.append(DiffToken("".join(a_toks[i1:i2]), "delete"))
                v2_out.append(DiffToken("".join(b_toks[j1:j2]), "insert"))
        return v1_out, v2_out

    # UC-02 Document Comparison
    def compare_documents(self, v1_text: str, v2_text: str) -> ComparisonResult:
        v1_lines = v1_text.splitlines()
        v2_lines = v2_text.splitlines()
        sm = difflib.SequenceMatcher(a=v1_lines, b=v2_lines, autojunk=False)
        blocks: list[DiffBlock] = []
        risk: list[RiskFlag] = []
        # Count actual content changed (lines), not opcode blocks — a single
        # "insert" opcode can span many lines, so block counts are misleading.
        added_lines = removed_lines = modified_lines = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            v1_chunk = "\n".join(v1_lines[i1:i2])
            v2_chunk = "\n".join(v2_lines[j1:j2])
            v1_tokens = v2_tokens = None
            if tag == "equal":
                blocks.append(DiffBlock(kind=tag, v1=v1_chunk, v2=v2_chunk))
                continue
            if tag == "insert":
                added_lines += j2 - j1
            elif tag == "delete":
                removed_lines += i2 - i1
            elif tag == "replace":
                modified_lines += max(i2 - i1, j2 - j1)
                # Word-level diff so the UI can pinpoint the exact tokens that changed.
                v1_tokens, v2_tokens = self._word_diff(v1_chunk, v2_chunk)
            blocks.append(
                DiffBlock(kind=tag, v1=v1_chunk, v2=v2_chunk, v1_tokens=v1_tokens, v2_tokens=v2_tokens)
            )
            combined = (v1_chunk + " " + v2_chunk).lower()
            for kw in _MATERIAL_KEYWORDS:
                if kw in combined:
                    excerpt = (v2_chunk or v1_chunk).strip()[:240]
                    risk.append(
                        RiskFlag(
                            severity="high" if kw in ("liability", "indemnif", "termination") else "medium",
                            excerpt=excerpt,
                            rationale=f'Material change near "{kw}" — review for commercial/legal impact.',
                        )
                    )
                    break
        summary = (
            f"{added_lines} line(s) added, {removed_lines} removed, {modified_lines} modified. "
            f"{len(risk)} change(s) flagged on material terms."
        )
        return ComparisonResult(
            diff_blocks=blocks, risk_commentary=risk, summary_report=summary, model_version=self.model_version
        )

    def summarize_document_changes(
        self,
        v1_text: str,
        v2_text: str,
        diff_blocks: list[DiffBlock],
        risk_commentary: list[RiskFlag],
        contract_type: str = "MSA",
    ) -> NegotiationChangeSummary:
        changes: list[NegotiationChangeItem] = []
        idx = 0
        for i, block in enumerate(diff_blocks):
            if block.kind == "equal":
                continue
            old_t = (block.v1 or "").strip()[:500]
            new_t = (block.v2 or "").strip()[:500]
            combined = (old_t + " " + new_t).lower()
            severity, matched_kw, why = _classify_change(combined)

            clause_ref = _nearest_heading(diff_blocks, i)
            change_summary = _change_summary(block)

            verb = {"insert": "added", "delete": "removed", "replace": "modified"}.get(block.kind, "changed")
            subject = matched_kw.title() if matched_kw else "Contract"
            title = f"{subject} terms {verb}"
            if clause_ref:
                title = f"{clause_ref}: {subject.lower()} terms {verb}"

            impact = (
                f"Vendor {verb} {contract_type} terms here. {why} "
                "Review for alignment with the JFPSL playbook."
            )
            if severity in ("high", "medium"):
                action = (
                    "Counter-propose the JFPSL standard position"
                    + (" and escalate to Legal Admin." if severity == "high" else ".")
                )
                rationale = (
                    f"Flagged {severity} because the change touches {matched_kw or 'material'} terms. {why}"
                )
            else:
                action = "Confirm acceptable or note for final review."
                rationale = why
            changes.append(
                NegotiationChangeItem(
                    diff_index=i,
                    title=title[:140],
                    old_text=old_t,
                    new_text=new_t,
                    severity=severity,
                    impact=impact,
                    suggested_action=action,
                    clause_ref=clause_ref,
                    change_summary=change_summary,
                    rationale=rationale,
                )
            )
            idx += 1
            if idx >= 25:
                break
        for rf in risk_commentary[:5]:
            if any(c.severity == rf.severity and rf.excerpt[:80] in c.old_text for c in changes):
                continue
            changes.append(
                NegotiationChangeItem(
                    diff_index=-1,
                    title=f"Material term change ({rf.severity})",
                    old_text="",
                    new_text=rf.excerpt,
                    severity=rf.severity,
                    impact=rf.rationale,
                    suggested_action="Review flagged material change before next redline.",
                    clause_ref="",
                    change_summary=_condense(rf.excerpt, 90),
                    rationale=rf.rationale,
                )
            )
        exec_summary = (
            f"{contract_type} negotiation: {len(changes)} material change(s) detected between versions. "
            f"{sum(1 for c in changes if c.severity == 'high')} high-severity item(s) require legal review."
        )
        if not changes:
            exec_summary = f"No material differences detected between {contract_type} versions."
        return NegotiationChangeSummary(
            changes=changes,
            executive_summary=exec_summary,
            model_version=self.model_version,
        )

    # UC-03 LegalBot
    def answer_legal_bot(self, question: str, knowledge_base: Sequence[Any]) -> LegalBotResult:
        q_lc = question.lower()
        best: tuple[Any, int] | None = None
        for entry in knowledge_base:
            keywords = [k.lower() for k in (entry.keywords or [])]
            hits = sum(1 for kw in keywords if kw and kw in q_lc)
            if hits and (best is None or hits > best[1]):
                best = (entry, hits)
        if best is None:
            return LegalBotResult(
                answer=(
                    "I couldn't find a confident match for this question in JFPSL's legal knowledge base. "
                    "Escalating to the Legal team for review."
                ),
                citations=[],
                confidence=0.25,
                tier=2,
                model_version=self.model_version,
            )
        entry, hits = best
        confidence = min(0.95, 0.4 + 0.15 * hits)
        tier = 1 if confidence >= _TIER1_THRESHOLD else 2
        return LegalBotResult(
            answer=entry.answer,
            citations=list(entry.citations or []),
            confidence=round(confidence, 2),
            tier=tier,
            model_version=self.model_version,
        )

    # UC-04 Legal Research
    def generate_research_note(self, query: str, regulatory_corpus: Sequence[Any]) -> ResearchResult:
        q_lc = query.lower()
        scored: list[tuple[Any, int]] = []
        terms = [t for t in re.split(r"\W+", q_lc) if len(t) > 3]
        for entry in regulatory_corpus:
            text = (entry.title + " " + entry.content).lower()
            tag_score = sum(2 for t in (entry.tags or []) if t.lower() in q_lc)
            term_score = sum(text.count(t) for t in terms)
            score = tag_score + term_score
            if score > 0:
                scored.append((entry, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:5]
        citations = [
            {
                "regulator": e.regulator,
                "reference": e.reference,
                "title": e.title,
                "score": s,
            }
            for e, s in top
        ]
        applicable = [{"regulator": e.regulator, "reference": e.reference} for e, _ in top]
        provisions = [
            {"reference": e.reference, "excerpt": (e.content or "")[:280]} for e, _ in top
        ]
        if not top:
            summary = (
                f"No matching documents found in the indexed JFPSL regulatory corpus for query: "
                f'"{query[:140]}". Recommend expanding the corpus or refining the query.'
            )
            implications = (
                "No corpus hits — implications cannot be drawn without additional sources. "
                "Hallucination guard prevented external citations."
            )
            next_steps = ["Refine query terms.", "Ingest additional regulatory sources.", "Escalate to Legal Head."]
            confidence = 0.2
        else:
            summary = (
                f"Found {len(top)} relevant source(s) in the JFPSL regulatory corpus. "
                f"Top regulator(s): {', '.join(sorted({e.regulator for e, _ in top}))}. "
                f"Strongest match: {top[0][0].reference}."
            )
            implications = (
                f"Based on the indexed corpus, JFPSL must align its position on this matter with "
                f"{top[0][0].regulator}'s guidance under {top[0][0].reference}. "
                f"This is an AI-drafted starting point — human legal validation is required before action."
            )
            next_steps = [
                "Review the full text of each cited source.",
                "Map specific JFPSL product / contract implications.",
                "Circulate draft note with Legal Head for sign-off.",
            ]
            confidence = round(min(0.9, 0.45 + 0.1 * len(top)), 2)
        return ResearchResult(
            summary=summary,
            applicable_regulations=applicable,
            key_provisions=provisions,
            implications=implications,
            recommended_next_steps=next_steps,
            citations=citations,
            confidence=confidence,
            model_version=self.model_version,
        )

    # Task Manager: extraction + priority
    def extract_tasks_from_email(
        self,
        sender_name: str,
        sender_email: str,
        subject: str,
        body: str,
        thread_summary: str = "",
        allow_fallback: bool = True,
    ) -> list[ExtractedTask]:
        from datetime import datetime, timedelta, timezone

        action_phrases = [
            "please review",
            "kindly",
            "can you",
            "could you",
            "need to",
            "needs to",
            "have to",
            "follow up",
            "follow-up",
            "send across",
            "share the",
            "share with",
            "draft the",
            "prepare the",
            "circulate",
            "confirm if",
            "confirm whether",
            "let me know",
            "by eod",
            "by tomorrow",
            "by friday",
            "by monday",
            "deadline",
            "due by",
            "expected by",
            "looking for your",
            "awaiting",
            "approve the",
            "sign off",
            "sign-off",
            "review and",
            "action required",
        ]

        sentences = re.split(r"(?<=[.!?])\s+", body.strip())
        tasks: list[ExtractedTask] = []
        seen: set[str] = set()
        now = datetime.now(timezone.utc)

        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 12:
                continue
            s_lc = s_clean.lower()
            if not any(p in s_lc for p in action_phrases):
                continue
            title = s_clean.rstrip(".!?")[:140]
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            due = _guess_due_date(s_lc, now)
            est = _guess_estimate(s_lc)
            priority, score, rationale = self.score_task_priority(
                title=title, description=s_clean, sender_email=sender_email, due_date=due
            )
            tasks.append(
                ExtractedTask(
                    title=title,
                    description=f'Extracted from "{subject}" — {sender_name} <{sender_email}>.',
                    priority=priority,
                    priority_score=score,
                    confidence=round(min(0.95, 0.55 + 0.07 * sum(1 for p in action_phrases if p in s_lc)), 2),
                    rationale=rationale,
                    due_date=due,
                    tags=_derive_tags(s_lc + " " + subject.lower()),
                    estimated_minutes=est,
                    model_version=self.model_version,
                )
            )

        # Fallback — manual ingest only when allowed.
        if not tasks and allow_fallback:
            title = f"Review email: {subject[:120]}"
            priority, score, rationale = self.score_task_priority(
                title=title, description=body[:300], sender_email=sender_email, due_date=None
            )
            tasks.append(
                ExtractedTask(
                    title=title,
                    description=f"Inbound email from {sender_name} <{sender_email}>. No explicit action item detected; review and triage.",
                    priority=priority,
                    priority_score=score,
                    confidence=0.4,
                    rationale=rationale + " (No explicit action items detected; default review task.)",
                    due_date=None,
                    tags=_derive_tags(subject.lower() + " " + body.lower()[:400]),
                    estimated_minutes=10,
                    model_version=self.model_version,
                )
            )
        return tasks[:3]

    def generate_email_reply(
        self,
        latest_body: str,
        original_subject: str,
        from_addr: str,
        prior_summary: str = "",
        user_feedback: str | None = None,
    ) -> EmailReplyResult:
        subj = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
        opener = "Dear colleague,\n\nThank you for your email."
        if user_feedback:
            opener = f"Dear colleague,\n\nThank you for your email. Per your guidance: {user_feedback.strip()}"
        body = (
            f"{opener}\n\n"
            "We have reviewed the matter and will revert with a formal position shortly. "
            "Please let us know if any urgent deadline applies.\n\n"
            "Regards,\nJFPSL Legal Team"
        )
        if latest_body.strip():
            excerpt = latest_body.strip()[:200].replace("\n", " ")
            body = (
                f"{opener}\n\n"
                f"We acknowledge your message regarding \"{excerpt}…\" and are reviewing internally. "
                "We will respond with our position at the earliest.\n\n"
                "Regards,\nJFPSL Legal Team"
            )
        return EmailReplyResult(
            subject=subj[:500],
            body=body,
            confidence=0.62,
            rationale="Deterministic stub reply — human review required before send.",
            model_version=self.model_version,
        )

    def score_task_priority(
        self,
        title: str,
        description: str | None,
        sender_email: str | None,
        due_date: Any,
    ) -> tuple[str, float, str]:
        from datetime import datetime, timezone

        text = (title + " " + (description or "")).lower()
        score = 0.0
        reasons: list[str] = []

        urgent_words = ["urgent", "asap", "immediately", "today", "critical", "p0", "emergency"]
        if any(w in text for w in urgent_words):
            score += 35
            reasons.append("urgency language")
        important_words = ["important", "priority", "tomorrow", "by eod", "soon", "p1", "high priority"]
        if any(w in text for w in important_words):
            score += 18
            reasons.append("priority signal")

        if sender_email:
            s = sender_email.lower()
            seniority = ["ceo", "cto", "cfo", "coo", "cro", "ciso", "chief", "head", "vp", "president"]
            if any(role in s for role in seniority):
                score += 22
                reasons.append("senior sender")

        regulator_words = [
            "rbi",
            "sebi",
            "irdai",
            "regulator",
            "regulatory",
            "compliance",
            "circular",
            "show-cause",
            "show cause",
            "audit",
            "inspection",
            "kfs",
            "dpdp",
            "pmla",
            "fiu",
        ]
        if any(w in text for w in regulator_words):
            score += 16
            reasons.append("regulatory context")

        legal_critical = ["litigation", "notice", "ombudsman", "breach", "indemnity", "termination"]
        if any(w in text for w in legal_critical):
            score += 14
            reasons.append("legal-critical term")

        if due_date is not None:
            try:
                delta = (due_date - datetime.now(timezone.utc)).total_seconds() / 86400.0
            except Exception:
                delta = None
            if delta is not None:
                if delta <= 0:
                    score += 35
                    reasons.append("overdue or due today")
                elif delta <= 1:
                    score += 22
                    reasons.append("due within 24h")
                elif delta <= 3:
                    score += 12
                    reasons.append("due within 3 days")
                elif delta <= 7:
                    score += 6
                    reasons.append("due this week")

        if score >= 55:
            label = "P0"
        elif score >= 32:
            label = "P1"
        elif score >= 15:
            label = "P2"
        else:
            label = "P3"
        rationale = (
            f"Priority {label} (score {round(score)}). " + ("; ".join(reasons) + "." if reasons else "No strong signals; default low priority.")
        )
        return label, round(score, 1), rationale

    # Prompt-based document editing
    def edit_document(
        self,
        base_text: str,
        instruction: str,
        selection: str | None = None,
    ) -> DocumentEditResult:
        """Rule-based document edit for local dev without an LLM.

        Handles common legal edit patterns (replace text, liability caps, DPDP
        clauses, removals). Set AI_BACKEND=adk for free-form prompt editing.
        """
        return _stub_edit_document(base_text, instruction, selection, self.model_version)

    def plan_docx_operations(
        self,
        structure: dict[str, Any],
        instruction: str,
        selection: str | None = None,
        edit_memory: list[str] | None = None,
        full_text: str | None = None,
    ) -> DocxEditPlanResult:
        return _stub_plan_docx_operations(
            structure, instruction, selection, edit_memory, self.model_version, full_text
        )

    # UC-06 Legal News
    def analyse_regulatory_update(self, source: str, title: str, full_text: str) -> NewsAnalysis:
        combined = (title + " " + full_text).lower()
        category_keywords = {
            "Lending": ["loan", "lending", "credit", "nbfc", "co-lending", "kfs", "fair practice"],
            "Insurance": ["insurance", "irdai", "insurer", "policyholder"],
            "Payments": ["payment", "upi", "ppi", "prepaid", "p2p"],
            "Investments": ["mutual fund", "sebi", "amc", "advisory", "investment"],
            "Data Privacy": ["dpdp", "personal data", "privacy", "consent", "processor"],
            "AML/KYC": ["aml", "kyc", "pmla", "fiu", "money laundering"],
        }
        tags = [cat for cat, kws in category_keywords.items() if any(kw in combined for kw in kws)]
        hits = sum(1 for kws in category_keywords.values() for kw in kws if kw in combined)
        relevance = round(min(1.0, 0.2 + 0.05 * hits), 2)
        # 3-5 line summary: first sentences truncated.
        sentences = re.split(r"(?<=[.!?])\s+", full_text.strip())
        summary = " ".join(sentences[:4])[:600] or title
        return NewsAnalysis(
            summary=summary,
            tags=tags,
            relevance_score=relevance,
            model_version=self.model_version,
            category=tags[0] if tags else "Other",
        )


_FLAG_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def max_flag(a: str, b: str) -> str:
    return a if _FLAG_ORDER.get(a, 0) >= _FLAG_ORDER.get(b, 0) else b


# ── Task extraction helpers ──────────────────────────────────────────────────

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _guess_due_date(text_lc: str, now):
    """Heuristic date extraction. Returns datetime or None."""
    from datetime import datetime, timedelta

    if "today" in text_lc or "by eod" in text_lc or "end of day" in text_lc:
        return now.replace(hour=18, minute=0, second=0, microsecond=0)
    if "tomorrow" in text_lc:
        return (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    if "by next week" in text_lc or "next week" in text_lc:
        return (now + timedelta(days=7)).replace(hour=18, minute=0, second=0, microsecond=0)
    if "this week" in text_lc or "by friday" in text_lc:
        # Set to upcoming Friday
        days_ahead = (4 - now.weekday()) % 7 or 7
        return (now + timedelta(days=days_ahead)).replace(hour=18, minute=0, second=0, microsecond=0)

    for day, idx in _WEEKDAYS.items():
        if f"by {day}" in text_lc or f"on {day}" in text_lc:
            days_ahead = (idx - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).replace(hour=18, minute=0, second=0, microsecond=0)

    # Numeric like "in 3 days"
    m = re.search(r"in (\d{1,2}) day", text_lc)
    if m:
        return (now + timedelta(days=int(m.group(1)))).replace(hour=18, minute=0, second=0, microsecond=0)
    return None


def _guess_estimate(text_lc: str) -> int | None:
    """Light-weight guess for estimated minutes based on complexity hints."""
    if any(w in text_lc for w in ["full review", "thorough", "draft from scratch", "negotiate", "research"]):
        return 60
    if any(w in text_lc for w in ["review", "comment", "redline", "respond"]):
        return 30
    if any(w in text_lc for w in ["confirm", "acknowledge", "approve", "sign", "share"]):
        return 10
    return None


def _derive_tags(text_lc: str) -> list[str]:
    tag_map = {
        "Contract": ["msa", "nda", "contract", "agreement", "redline", "clause"],
        "Regulatory": ["rbi", "sebi", "irdai", "regulator", "circular", "compliance", "dpdp", "pmla"],
        "Litigation": ["litigation", "notice", "court", "ombudsman", "show-cause"],
        "Data Privacy": ["dpdp", "privacy", "personal data", "consent", "breach"],
        "Product Legal": ["product", "feature", "launch", "kfs", "marketing", "t&c"],
        "Finance": ["payment", "invoice", "fees", "remittance", "lrs"],
    }
    found = [tag for tag, kws in tag_map.items() if any(kw in text_lc for kw in kws)]
    return found[:3]
