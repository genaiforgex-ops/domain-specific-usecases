from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GmailSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    poll_enabled: bool
    poll_labels: list[str]
    auto_task_ingest: bool
    poll_lookback_days: int = 7
    watched_threads: list[dict] = Field(default_factory=list)
    watched_senders: list[str] = Field(default_factory=list)
    msa_watched_threads: list[dict] = Field(default_factory=list)
    default_context_module: str
    last_poll_at: datetime | None
    connected: bool = False
    email: str | None = None


class GmailSettingsUpdate(BaseModel):
    poll_enabled: bool | None = None
    poll_labels: list[str] | None = None
    auto_task_ingest: bool | None = None
    poll_lookback_days: int | None = Field(default=None, ge=1, le=30)
    watched_threads: list[dict] | None = None
    watched_senders: list[str] | None = None
    msa_watched_threads: list[dict] | None = None
    default_context_module: str | None = None


class WatchedThreadIn(BaseModel):
    thread_id: str
    subject: str | None = None
    from_addr: str | None = None


class WatchedSenderIn(BaseModel):
    email: str


class GmailLabelOut(BaseModel):
    id: str
    name: str
    type: str


class GmailMessageSummary(BaseModel):
    id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    snippet: str
    date: str | None = None


class GmailMessageListOut(BaseModel):
    messages: list[GmailMessageSummary]
    next_page_token: str | None = None


class GmailMessageOut(BaseModel):
    id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    body: str
    date: str | None = None


class GmailThreadOut(BaseModel):
    id: str
    messages: list[GmailMessageOut]


class EmailDraftCreate(BaseModel):
    gmail_thread_id: str
    gmail_message_id: str
    user_feedback: str | None = None


class EmailDraftUpdate(BaseModel):
    draft_subject: str | None = None
    draft_body: str | None = None
    user_feedback: str | None = None
    status: str | None = None
    remind_at: datetime | None = None


class EmailDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    user_id: int
    task_id: int | None = None
    auto_generated: bool = False
    gmail_thread_id: str
    gmail_message_id: str
    original_subject: str
    original_body: str
    from_addr: str
    to_addr: str | None
    draft_subject: str
    draft_body: str
    status: str
    user_feedback: str | None
    remind_at: datetime | None
    model_version: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmailDraftApprove(BaseModel):
    remind_in_hours: int = Field(default=2, ge=0, le=168)
