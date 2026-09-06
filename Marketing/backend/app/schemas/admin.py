"""Admin DTOs — the cross-pipeline oversight payload for the Admin dashboard."""

import uuid

from datetime import date, datetime

from pydantic import BaseModel


class RoleDefaultOut(BaseModel):
    """The account new work auto-routes to for one role (null if unset)."""

    role: str
    role_label: str
    user_id: uuid.UUID | None = None
    full_name: str | None = None


class RoleDefaultSet(BaseModel):
    """Point a role's default at a user."""

    user_id: uuid.UUID


class TrendPoint(BaseModel):
    """One point in a time-series — a date bucket and its value (spend or count)."""

    bucket: date
    value: float


class OperationTrendPoint(BaseModel):
    """One (day, operation) spend bucket — the operation-split spend trend."""

    bucket: date
    operation: str
    value: float


class StageCounts(BaseModel):
    """How many briefs sit in each pipeline stage right now."""

    draft: int
    brief_review: int
    copywriting: int
    design: int
    creative_review: int
    final_signoff: int
    completed: int


class StatusCounts(BaseModel):
    draft: int
    submitted: int
    approved: int
    changes_requested: int


class PendingWork(BaseModel):
    """Open work items, by the person they're waiting on."""

    brief_review_total: int  # briefs awaiting the Marketing Lead's brief review
    awaiting_copy: int  # copywriting stage, nothing written yet
    copywriting_total: int  # all briefs with the Copywriter
    design_total: int  # briefs with the Designer, not yet exported
    creative_review_total: int  # briefs awaiting the Marketing Lead's creative review
    final_signoff_total: int  # briefs awaiting the Product Lead's final sign-off


class CostingOp(BaseModel):
    """Per-operation rollup of traced model calls."""

    operation: str  # brief_extract | copy_generation | banner_image
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    avg_latency_ms: int
    cost_inr: float


class Costing(BaseModel):
    """Real AI spend, derived from logged token usage on every model call."""

    total_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_inr: float
    avg_latency_ms: int
    by_operation: list[CostingOp]


class AiCallItem(BaseModel):
    """One traced model call — the raw row behind the costing rollups."""

    id: uuid.UUID
    operation: str
    model: str
    brief_id: uuid.UUID | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    cost_inr: float
    status: str
    at: datetime


# ── Granular costing breakdown (the dedicated Costing page) ───────────────────


class CostingWindows(BaseModel):
    today_inr: float
    week_inr: float
    total_inr: float


class CostingTotals(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_inr: float
    avg_latency_ms: int


class CostingOpDetail(BaseModel):
    """One operation's spend, with the input/output cost split called out."""

    operation: str
    calls: int
    input_tokens: int
    output_tokens: int
    input_cost_inr: float
    output_cost_inr: float
    cost_inr: float
    avg_latency_ms: int


class CostingModel(BaseModel):
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_inr: float


class CostingBrief(BaseModel):
    brief_id: uuid.UUID | None
    title: str
    calls: int
    total_tokens: int
    cost_inr: float


class CostingDetail(BaseModel):
    """The full granular costing payload for the Admin Costing page."""

    windows: CostingWindows
    totals: CostingTotals
    spend_trend: list[TrendPoint]  # daily spend buckets, oldest → newest
    spend_by_operation_trend: list[OperationTrendPoint]  # daily, split by operation
    by_operation: list[CostingOpDetail]
    by_model: list[CostingModel]
    by_brief: list[CostingBrief]
    recent_calls: list[AiCallItem]


class Throughput(BaseModel):
    exported: int  # briefs shipped to Figma
    change_requests: int  # times a brief was bounced for changes
    avg_lead_time_hours: float | None  # created → exported, averaged over shipped briefs


class PendingItem(BaseModel):
    """A brief sitting in a non-terminal stage, with how long it's been waiting."""

    id: uuid.UUID
    title: str
    stage: str
    waiting_days: int
    updated_at: datetime


class FilterOptions(BaseModel):
    """The distinct values the dashboard filters can offer (users come from the
    account directory the client already loads)."""

    products: list[str]


class AdminBriefRow(BaseModel):
    """One brief in the filtered oversight list the KPI cards deep-link into."""

    id: uuid.UUID
    title: str
    stage: str
    status: str
    product: str | None
    waiting_days: int
    updated_at: datetime
    exported: bool


class AdminOverview(BaseModel):
    totals: StageCounts
    by_status: StatusCounts
    pending: PendingWork
    costing: Costing
    throughput: Throughput
    oldest_pending: list[PendingItem]
    spend_trend: list[TrendPoint]
    throughput_trend: list[TrendPoint]
    filter_options: FilterOptions
