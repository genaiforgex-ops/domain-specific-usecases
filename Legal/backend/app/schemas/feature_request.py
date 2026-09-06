from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeatureRequestCreate(BaseModel):
    title: str = Field(min_length=4, max_length=512)
    description: str = Field(min_length=10)
    request_type: str = "feature"
    priority: str | None = None  # AI auto-scores if omitted
    repository: str | None = None


class FeatureRequestUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None


class AgentLogEntry(BaseModel):
    at: datetime
    level: str  # info | warn | error | success
    stage: str
    message: str


class FeatureRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    title: str
    description: str
    request_type: str
    priority: str
    priority_score: float
    status: str
    repository: str | None
    github_issue_number: int | None
    github_issue_url: str | None
    branch_name: str | None
    pr_number: int | None
    pr_url: str | None
    deployment_url: str | None
    plan: list | None
    files_touched: list | None
    loc_estimate: int | None
    diff_summary: str | None
    agent_log: list
    model_version: str | None
    created_by_id: int
    approved_by_id: int | None
    created_at: datetime
    updated_at: datetime
    state_changed_at: datetime
    pr_opened_at: datetime | None
    merged_at: datetime | None
    deployed_at: datetime | None


class FeatureRequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    request_type: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
