from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContractCreate(BaseModel):
    filename: str
    contract_type: str = "MSA"
    raw_text: str
    review_guidelines: str | None = None


class ContractRunReviewRequest(BaseModel):
    review_guidelines: str | None = None


class ContractSuggestionDecision(BaseModel):
    suggestion_id: int
    decision: str  # accept | modify | reject
    reviewer_edit: str | None = None


class ContractSuggestionsApply(BaseModel):
    edited_text: str = ""
    change_mode: str = "track"
    force: bool = False


class ReviewFindingOut(BaseModel):
    order_index: int
    heading: str | None = None
    clause_text: str
    risk_flag: str
    confidence: float
    rationale: str
    ai_suggestion: str | None = None
    original_text: str | None = None
    proposed_text: str | None = None
    category: str | None = None
    decision: str = "pending"
    reviewer_edit: str | None = None
    playbook_clause_id: int | None = None
    playbook_clause_type: str | None = None
    standard_position_excerpt: str | None = None
    clause_bank_id: int | None = None
    regulatory_ref: str | None = None


class ContractSuggestionsPreview(BaseModel):
    base_text: str
    edited_text: str
    diff_blocks: list[dict]
    applied_count: int
    blocked_count: int
    accepted_count: int
    applied: list[dict] = []
    blocked: list[dict] = []


class ContractChangesOut(BaseModel):
    change_history: list[dict] = []


class ClauseDecision(BaseModel):
    decision: str  # accepted | rejected | edited
    reviewer_edit: str | None = None
    reviewer_comment: str | None = None


class ContractClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_index: int
    heading: str | None
    clause_text: str
    risk_flag: str
    confidence: float
    ai_rationale: str | None
    ai_suggestion: str | None
    decision: str
    reviewer_edit: str | None
    reviewer_comment: str | None
    references: list | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    filename: str
    contract_type: str
    raw_text: str
    risk_score: float | None
    status: str
    model_version: str | None
    uploaded_by_id: int
    reviewed_by_id: int | None
    created_at: datetime
    reviewed_at: datetime | None
    review_guidelines: str | None = None
    ai_suggestions: list | None = None
    change_history: list | None = None
    risk_breakdown: dict | None = None
    playbook_summary: dict | None = None
    clauses: list[ContractClauseOut] = []


class ContractSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    contract_type: str
    risk_score: float | None
    status: str
    created_at: datetime


# ── Prompt-based document editing (UC-01) ──────────────────────────────────────


class PromptEditCreate(BaseModel):
    instruction: str
    selection: str | None = None


class EditChangeOut(BaseModel):
    description: str
    original: str
    revised: str


class DiffBlockOut(BaseModel):
    kind: str  # equal | insert | delete | replace
    v1: str
    v2: str


class ContractRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    contract_id: int
    instruction: str
    selection: str | None
    base_text: str
    edited_text: str
    change_summary: str | None
    changes: list[EditChangeOut] | None = None
    diff_blocks: list[DiffBlockOut] | None = None
    status: str
    model_version: str | None
    created_by_id: int
    created_at: datetime
    applied_at: datetime | None


class ContractRevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    instruction: str
    change_summary: str | None
    status: str
    created_at: datetime
    applied_at: datetime | None
