from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str | None = None  # if omitted, AI scores it
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    tags: list[str] = []
    assigned_to_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    tags: list[str] | None = None
    assigned_to_id: int | None = None


class TaskIngestEmail(BaseModel):
    sender_name: str
    sender_email: EmailStr
    subject: str
    body: str
    received_at: datetime | None = None


class TaskSnooze(BaseModel):
    snoozed_until: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    title: str
    description: str | None
    source: str
    source_module: str | None
    source_ref_id: int | None
    email_sender: str | None
    email_subject: str | None
    email_body: str | None
    gmail_message_id: str | None = None
    gmail_thread_id: str | None = None
    priority: str
    priority_score: float
    status: str
    due_date: datetime | None
    estimated_minutes: int | None
    snoozed_until: datetime | None
    created_by_id: int
    assigned_to_id: int | None
    tags: list
    ai_confidence: float | None
    ai_rationale: str | None
    model_version: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskAggregated(BaseModel):
    """A virtual task derived from another module's state. Not persisted unless
    the user explicitly promotes it.
    """
    key: str  # stable identifier, e.g. "contract:42"
    title: str
    description: str
    source_module: str
    source_ref_id: int
    priority: str
    priority_score: float
    due_date: datetime | None = None
    tags: list[str] = []


class DailyBrief(BaseModel):
    summary: str
    counts: dict[str, int]
    streak_days: int
    completed_today: int
    overdue: int
    new_gmail_tasks_count: int = 0
    pending_email_drafts: int = 0
    top_priorities: list[TaskOut]
    aggregated_suggestions: list[TaskAggregated]
