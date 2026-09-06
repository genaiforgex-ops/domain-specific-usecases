from datetime import date, datetime

from pydantic import BaseModel


class MetricsSummaryOut(BaseModel):
    total_users: int
    active_users: int
    total_documents: int
    total_queries: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    ai_actions: int


class DailyCountOut(BaseModel):
    day: date
    count: int


class DailyTokenOut(BaseModel):
    day: date
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ModuleDailyOut(BaseModel):
    day: date
    module: str
    count: int


class UserSegmentOut(BaseModel):
    segment: str
    label: str
    query_range: str
    count: int
    percentage: float


class MetricsUserRowOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    role: str
    documents: int
    queries: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    last_login_at: datetime | None


class MetricsUsersPageOut(BaseModel):
    items: list[MetricsUserRowOut]
    total: int
    page: int
    page_size: int


class ModuleUsageOut(BaseModel):
    module: str
    label: str
    count: int


class ChatFeedbackSummaryOut(BaseModel):
    up: int
    down: int
    commented: int
    total_rated: int
    recent: list[dict]
