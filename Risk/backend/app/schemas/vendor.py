from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class VendorCreate(BaseModel):
    legal_name: str
    country: str = "IN"
    cin: str | None = None
    pan: str | None = None
    gstin: str | None = None
    website: str | None = None
    registered_address: str | None = None


class VendorResponse(ORMBase):
    id: UUID
    legal_name: str
    country: str
    cin: str | None
    pan: str | None
    gstin: str | None
    website: str | None
    created_at: datetime


class DDFindingUpdate(BaseModel):
    disposition: str = Field(pattern="^(true_positive|false_positive|needs_clarification)$")


class DDFindingResponse(ORMBase):
    id: UUID
    category: str
    title: str
    summary: str | None
    source_tier: str
    source_url: str | None
    disposition: str | None
    severity_weight: float


class DDReportResponse(ORMBase):
    id: UUID
    vendor_id: UUID
    status: str
    red_flag_score: float | None
    weights_version: str | None
    outsourcing_checklist: str | None
    audit_data: dict | None = None
    error: str | None = None
    findings: list[DDFindingResponse] = []
    created_at: datetime


class DDWeightUpdate(BaseModel):
    category_weights: dict[str, float]
