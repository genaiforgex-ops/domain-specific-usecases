from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComparisonCreate(BaseModel):
    label: str
    v1_filename: str
    v2_filename: str
    v1_text: str
    v2_text: str


class DiffToken(BaseModel):
    text: str
    op: str  # equal | insert | delete


class DiffBlock(BaseModel):
    kind: str  # equal | insert | delete | replace
    v1: str
    v2: str
    # Word-level breakdown, present for "replace" blocks (null otherwise).
    v1_tokens: list[DiffToken] | None = None
    v2_tokens: list[DiffToken] | None = None


class RiskFlag(BaseModel):
    severity: str
    excerpt: str
    rationale: str


class ComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    label: str
    v1_filename: str
    v2_filename: str
    diff_blocks: list[dict]
    risk_commentary: list[dict]
    summary_report: str
    model_version: str | None
    created_at: datetime


class ComparisonSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    v1_filename: str
    v2_filename: str
    created_at: datetime
