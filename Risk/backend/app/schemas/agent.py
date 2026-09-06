from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    rbi_prompt: str = Field(min_length=1)
    sebi_prompt: str = Field(min_length=1)
    model_version: str = "gemini-2.5-flash"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class AgentUpdate(BaseModel):
    # All optional — PATCH only touches the fields that are sent. is_active=False
    # is how the API archives an agent.
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    rbi_prompt: str | None = Field(default=None, min_length=1)
    sebi_prompt: str | None = Field(default=None, min_length=1)
    model_version: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    is_active: bool | None = None


class AgentResponse(ORMBase):
    id: UUID
    name: str
    description: str | None
    rbi_prompt: str
    sebi_prompt: str
    model_version: str
    temperature: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AgentRunResponse(ORMBase):
    id: UUID
    agent_id: UUID | None
    agent_name: str
    status: str
    rbi_label: str | None
    rbi_confidence: float | None
    rbi_evidence: dict | None
    sebi_label: str | None
    sebi_confidence: float | None
    sebi_evidence: dict | None
    created_at: datetime


class AgentDefaults(BaseModel):
    rbi_prompt: str
    sebi_prompt: str
    model_version: str
    temperature: float
