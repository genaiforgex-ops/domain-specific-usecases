from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NewsIngest(BaseModel):
    source: str
    title: str
    full_text: str
    url: str | None = None
    published_at: datetime


class NewsTriage(BaseModel):
    status: str  # action_required | for_information | not_relevant
    impact_note: str | None = None


class NewsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    source_id: int | None = None
    category: str | None = None
    title: str
    summary: str
    full_text: str | None
    url: str | None
    tags: list
    relevance_score: float
    status: str
    published_at: datetime
    ingested_at: datetime
    triaged_by_id: int | None
    impact_note: str | None


# ── Tracked sources ────────────────────────────────────────────────────────────


class TrackedSourceCreate(BaseModel):
    name: str
    url: str
    regulator: str = "Other"
    category: str = "Other"
    source_type: str = "web"  # web | rss


class TrackedSourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    regulator: str | None = None
    category: str | None = None
    source_type: str | None = None
    enabled: bool | None = None


class TrackedSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    regulator: str
    category: str
    source_type: str
    enabled: bool
    last_fetched_at: datetime | None
    last_status: str | None
    created_at: datetime


# ── Discover / refresh / overview ────────────────────────────────────────────


class DiscoverResult(BaseModel):
    title: str
    url: str
    snippet: str


class DiscoverSaveRequest(BaseModel):
    url: str
    title: str
    regulator: str = "Web"
    category: str | None = None


class RefreshSummary(BaseModel):
    total_new: int
    action_required: int
    sources: list[dict]


class NewsOverview(BaseModel):
    total: int
    action_required: int
    new_this_week: int
    sources_count: int
    last_refreshed: datetime | None
