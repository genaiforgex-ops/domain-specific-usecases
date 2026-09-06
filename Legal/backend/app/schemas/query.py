from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueryCreate(BaseModel):
    question: str
    context_type: str = "none"  # none | msa_version | gmail_thread
    context_tracker_id: int | None = None
    context_version_id: int | None = None
    context_gmail_thread_id: str | None = None


class QueryOverride(BaseModel):
    legal_override: str


class QueryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    user_id: int
    question: str
    ai_answer: str | None
    citations: list | None
    confidence: float
    tier: int
    status: str
    legal_override: str | None
    overridden_by_id: int | None
    model_version: str | None
    context_type: str | None = None
    context_tracker_id: int | None = None
    context_version_id: int | None = None
    context_gmail_thread_id: str | None = None
    created_at: datetime
    resolved_at: datetime | None
    disclaimer: str = (
        "This is an AI-generated response for guidance only. "
        "For definitive legal advice, please escalate to the Legal team."
    )
