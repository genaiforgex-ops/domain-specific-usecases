"""Pydantic output schemas the ADK agents are forced to emit.

Setting `output_schema=` on an `LlmAgent` makes ADK constrain the model to
return JSON matching the schema, which we parse straight into these models —
no brittle free-text parsing, and a built-in hallucination guard (the model
cannot return fields we did not ask for).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskFlag = Literal["high", "medium", "low", "none"]
SuggestionCategory = Literal[
    "legal_risk",
    "policy",
    "grammar",
    "spelling",
    "ambiguity",
    "missing_clause",
    "definition",
]


# ── UC-01: review against standard position ────────────────────────────────────


class ClauseFinding(BaseModel):
    order_index: int = Field(description="0-based position of the clause in the document")
    heading: str | None = Field(default=None, description="Clause heading / number, if any")
    clause_text: str = Field(description="The clause text as it appears in the draft")
    risk_flag: RiskFlag = Field(description="Risk level of this clause for our side")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence 0..1")
    rationale: str = Field(description="Why this clause is flagged at this level")
    suggestion: str | None = Field(
        default=None,
        description="Preferred drafting / fallback per the standard position, if a change is advised",
    )
    original_text: str | None = Field(
        default=None,
        description="Exact excerpt from the draft to replace (required for actionable edits)",
    )
    proposed_text: str | None = Field(
        default=None,
        description="Replacement text for original_text (required for actionable edits)",
    )
    category: SuggestionCategory = Field(
        default="legal_risk",
        description="Finding type: legal_risk, policy, grammar, spelling, ambiguity, missing_clause, definition",
    )
    playbook_clause_type: str | None = Field(
        default=None,
        description="Playbook clause type this finding relates to, if any",
    )
    standard_position_excerpt: str | None = Field(
        default=None,
        description="Short excerpt of our standard position for this clause type",
    )
    regulatory_ref: str | None = Field(
        default=None,
        description="Regulatory reference if the finding touches regulated topics",
    )


class ReviewResult(BaseModel):
    clauses: list[ClauseFinding] = Field(default_factory=list)
    risk_score: float = Field(ge=0.0, le=100.0, description="Overall document risk 0..100")
    missing_clauses: list[str] = Field(
        default_factory=list,
        description="Clauses required by the standard position but absent from the draft",
    )


# ── Prompt-based document edit ─────────────────────────────────────────────────


class EditChange(BaseModel):
    description: str = Field(description="Plain-language description of this single change")
    original: str = Field(default="", description="Text removed/replaced (empty if pure insertion)")
    revised: str = Field(default="", description="Text inserted/replacing (empty if pure deletion)")


class DocumentEdit(BaseModel):
    edited_text: str = Field(description="The full document after applying the requested edit")
    change_summary: str = Field(description="One-paragraph summary of what was changed and why")
    changes: list[EditChange] = Field(
        default_factory=list, description="Itemised list of discrete changes made"
    )


# ── DOCX operation-based editing (high-fidelity) ───────────────────────────────


DocxOperationType = Literal[
    "insert_clause",
    "replace_clause",
    "delete_clause",
    "replace_span",
    "add_definition",
]


class DocxOperation(BaseModel):
    op_type: DocxOperationType = Field(description="Operation to perform on the DOCX structure")
    anchor_id: str | None = Field(
        default=None,
        description="Stable part ID for replace/delete targets (e.g. body:p:12)",
    )
    after_anchor_id: str | None = Field(
        default=None,
        description="Insert new content immediately after this part ID",
    )
    target_text: str | None = Field(
        default=None,
        description="Exact substring to replace within the anchored part",
    )
    content: str | None = Field(
        default=None,
        description="New clause text for insert/replace/add_definition operations",
    )
    description: str = Field(description="Plain-language description of this operation")
    confidence: float = Field(
        ge=0.0, le=1.0, default=0.8, description="Model confidence this op is correct"
    )


class DocxEditPlan(BaseModel):
    change_summary: str = Field(description="Summary of all planned operations")
    operations: list[DocxOperation] = Field(
        default_factory=list, description="Ordered list of DOCX edit operations"
    )


# ── Gmail: reply drafting & task extraction ────────────────────────────────────


class EmailReplyDraft(BaseModel):
    subject: str = Field(description="Reply subject line, typically Re: original")
    body: str = Field(
        description="ONLY the new reply text — do not quote or paste prior emails"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence the draft is appropriate")
    rationale: str = Field(description="One sentence on tone and key points covered")


class ExtractedEmailTaskItem(BaseModel):
    title: str = Field(description="Concise action item, max 120 chars")
    description: str = Field(description="What needs to be done")
    priority_hint: Literal["P0", "P1", "P2", "P3"] = Field(default="P2")
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_minutes: int | None = Field(default=None)


class EmailTaskExtractionResult(BaseModel):
    tasks: list[ExtractedEmailTaskItem] = Field(
        default_factory=list,
        description="Actionable tasks; empty if email is FYI with no action required",
    )


# ── UC-06: regulatory news analysis ────────────────────────────────────────────


class NewsAnalysisResult(BaseModel):
    summary: str = Field(description="3-5 sentence plain-English summary for in-house counsel")
    category: str = Field(
        description="One of: Banking, Lending, Payments, Securities, Insurance, "
        "Advertising, Data Protection, AML/KYC, Corporate, Other"
    )
    tags: list[str] = Field(default_factory=list, description="Up to 5 short topical tags")
    relevance_score: float = Field(
        ge=0.0, le=1.0, description="Relevance to a JFPSL (Indian financial-services) legal team"
    )
    impact_note: str = Field(
        default="", description="One line on the practical impact / recommended action, if any"
    )


# ── Legal Q&A / research (structured) ──────────────────────────────────────────


class LegalQAResult(BaseModel):
    answer: str = Field(description="Concise answer grounded in provided context only")
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)
    should_escalate: bool = Field(default=False)
    citation_notes: list[str] = Field(
        default_factory=list, description="Short source labels used in the answer"
    )


class ResearchNoteResult(BaseModel):
    summary: str = Field(description="Plain-English research summary")
    applicable_regulations: list[str] = Field(default_factory=list)
    key_provisions: list[str] = Field(default_factory=list)
    implications: str = Field(default="")
    recommended_next_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)


class ChangeSummaryItem(BaseModel):
    title: str
    old_text: str = ""
    new_text: str = ""
    severity: str = "medium"
    impact: str = ""
    suggested_action: str = ""
    clause_ref: str = ""
    change_summary: str = ""
    rationale: str = ""


class ChangeSummaryResult(BaseModel):
    executive_summary: str
    changes: list[ChangeSummaryItem] = Field(default_factory=list)


class GroundednessVerdict(BaseModel):
    """Whether one cited claim is actually supported by the excerpt it cites."""

    citation: int = Field(description="The [n] citation number being checked")
    supported: bool = Field(
        description="True only if the cited excerpt states or directly entails the claim"
    )
    reason: str = Field(default="", description="One short sentence explaining the verdict")


class GroundednessResult(BaseModel):
    verdicts: list[GroundednessVerdict] = Field(default_factory=list)
