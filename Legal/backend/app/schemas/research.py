from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResearchCreate(BaseModel):
    query: str


class ResearchUpdate(BaseModel):
    reviewer_notes: str | None = None
    status: str | None = None  # draft | finalized


class ResearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    query: str
    summary: str
    applicable_regulations: list
    key_provisions: list
    implications: str
    recommended_next_steps: list
    citations: list
    confidence: float
    status: str
    reviewer_notes: str | None
    model_version: str | None
    created_by_id: int
    finalized_by_id: int | None
    created_at: datetime
    finalized_at: datetime | None


class ResearchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    query: str
    status: str
    confidence: float
    created_at: datetime
