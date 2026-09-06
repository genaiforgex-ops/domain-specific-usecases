from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class ProjectCreate(BaseModel):
    name: str
    business_line: str | None = None
    vendor_id: UUID | None = None
    intake_data: dict = Field(default_factory=dict)


class ProjectResponse(ORMBase):
    id: UUID
    name: str
    business_line: str | None
    vendor_id: UUID | None
    intake_data: dict
    status: str
    created_at: datetime


class RiskScoreResponse(ORMBase):
    id: UUID
    project_id: UUID
    inherent_score: float
    residual_score: float | None
    final_inherent_score: float | None
    final_residual_score: float | None
    drivers: dict | None
    status: str
    override_justification: str | None
    created_at: datetime


class ScoreOverride(BaseModel):
    inherent_score: float
    residual_score: float
    justification: str = Field(min_length=20)


class WhatIfRequest(BaseModel):
    control_outcomes: dict[str, str] = Field(default_factory=dict)
