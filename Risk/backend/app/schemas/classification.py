from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.agent import AgentRunResponse
from app.schemas.common import ORMBase


class ClassificationConfirm(BaseModel):
    label: str | None = None
    source: str | None = None  # "rbi" or "sebi"


class ClassificationOverride(BaseModel):
    label: str
    justification: str = Field(min_length=20)
    # Optional "learning" loop: capture a prompt improvement and either append it
    # to an existing agent (in place) or seed a new agent from the prompt used
    # for this result. The learning goes only to the overridden regulator's prompt.
    source: str | None = None  # "rbi" or "sebi" — which regulator was overridden
    learning_info: str | None = None
    learning_mode: Literal["existing", "new"] | None = None
    target_agent_id: UUID | None = None  # when mode="existing"
    new_agent_name: str | None = None  # when mode="new"
    base_agent_id: UUID | None = None  # agent whose result was overridden; base for "new" (null = built-in default)


class ClassificationResponse(ORMBase):
    id: UUID
    vendor_id: UUID
    document_id: UUID | None
    document_filename: str | None = None
    input_text: str | None = None
    status: str
    ai_label: str | None
    ai_confidence: float | None
    ai_evidence: dict | None
    rbi_label: str | None
    rbi_confidence: float | None
    rbi_evidence: dict | None
    sebi_label: str | None
    sebi_confidence: float | None
    sebi_evidence: dict | None
    final_label: str | None
    justification: str | None
    requires_secondary_review: bool
    clause_library_version: str | None
    agent_runs: list[AgentRunResponse] = []
    created_at: datetime
    updated_at: datetime


class ClauseCreate(BaseModel):
    version: str
    regulator: str
    clause_ref: str
    text: str
    tags: str | None = None
    instrument: str | None = None
    source_doc: str | None = None
    page_no: int | None = None
    para_no: str | None = None


class ClauseResponse(ORMBase):
    id: UUID
    version: str
    regulator: str
    clause_ref: str
    text: str
    tags: str | None
    instrument: str | None = None
    source_doc: str | None = None
    page_no: int | None = None
    para_no: str | None = None
