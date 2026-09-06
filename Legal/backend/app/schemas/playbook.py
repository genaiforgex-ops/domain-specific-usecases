from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlaybookClauseCreate(BaseModel):
    clause_type: str
    contract_type: str = "MSA"
    standard_position: str
    risk_keywords: list[str] = []
    fallback_text: str | None = None
    regulatory_tags: list[str] = []
    is_required: bool = False
    insert_anchor_hint: str | None = None
    notes: str | None = None


class PlaybookClauseUpdate(BaseModel):
    clause_type: str | None = None
    contract_type: str | None = None
    standard_position: str | None = None
    risk_keywords: list[str] | None = None
    fallback_text: str | None = None
    regulatory_tags: list[str] | None = None
    is_required: bool | None = None
    insert_anchor_hint: str | None = None
    notes: str | None = None


class PlaybookClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clause_type: str
    contract_type: str
    standard_position: str
    risk_keywords: list[str]
    fallback_text: str | None
    regulatory_tags: list[str]
    is_required: bool
    insert_anchor_hint: str | None
    notes: str | None
    created_at: datetime


class PlaybookSummaryOut(BaseModel):
    contract_type: str
    clause_count: int
    required_count: int


class ClauseBankEntryCreate(BaseModel):
    playbook_clause_id: int | None = None
    contract_type: str = "MSA"
    clause_type: str
    tier: str = "preferred"
    title: str
    body_text: str
    version: int = 1
    is_active: bool = True
    regulatory_refs: list[str] = []


class ClauseBankEntryUpdate(BaseModel):
    playbook_clause_id: int | None = None
    contract_type: str | None = None
    clause_type: str | None = None
    tier: str | None = None
    title: str | None = None
    body_text: str | None = None
    version: int | None = None
    is_active: bool | None = None
    regulatory_refs: list[str] | None = None


class ClauseBankEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    playbook_clause_id: int | None
    contract_type: str
    clause_type: str
    tier: str
    title: str
    body_text: str
    version: int
    is_active: bool
    regulatory_refs: list
    created_at: datetime


class RegulatorySourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    regulator: str
    reference: str
    title: str
    tags: list
    published_on: datetime | None
    created_at: datetime


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic: str
    keywords: list[str]
    answer: str
    citations: list
    created_at: datetime


class ReviewChangeEntryOut(BaseModel):
    source: str
    status: str
    before: str | None = None
    after: str | None = None
    rationale: str | None = None
    playbook_clause_id: int | None = None
    decided_by_id: int | None = None
    order_index: int | None = None
    applied_at: str | None = None
