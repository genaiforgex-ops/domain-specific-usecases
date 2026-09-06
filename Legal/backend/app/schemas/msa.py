from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class MSAIngestEmail(BaseModel):
    """Simulates the Gmail ingest path for UC-05 in the absence of live OAuth.

    Production wires this to a Gmail API poller. For now, callers POST the
    parsed-out email + attachment text directly.
    """

    vendor_name: str
    vendor_email: EmailStr
    contract_type: str = "MSA"
    deal_reference: str | None = None
    subject: str
    body: str
    attachment_name: str
    attachment_text: str


class MSADecision(BaseModel):
    suggestion_id: int
    decision: str  # accept | modify | reject
    reviewer_edit: str | None = None


class MSADecideAll(BaseModel):
    decision: str = "accept"  # accept all pending


class MSAShareCreate(BaseModel):
    user_id: int
    access_level: str = "view"  # view | edit


class MSAShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracker_id: int
    user_id: int
    shared_by_id: int
    access_level: str
    shared_at: datetime
    user_email: str | None = None
    user_full_name: str | None = None


class ShareableUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str


class GroundTruthCheckOut(BaseModel):
    term: str
    passed: bool


class MSARiskBreakdown(BaseModel):
    overall: float
    from_ai_clauses: float
    from_ground_truth: int
    by_severity: dict[str, int]
    ground_truth_passed: int
    ground_truth_failed: int
    ground_truth_checks: list[GroundTruthCheckOut] = []


class NegotiationMemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracker_id: int
    kind: str
    content: str
    version_id: int | None
    created_by_id: int | None
    created_at: datetime


class MSARunReviewRequest(BaseModel):
    version_id: int | None = None
    review_guidelines: str | None = None


class MSASendEmail(BaseModel):
    subject: str
    body: str


class MSAGmailWatchIn(BaseModel):
    thread_id: str
    subject: str | None = None
    vendor_email: str | None = None


class MSAGmailWatchOut(BaseModel):
    thread_id: str
    tracker_id: int | None = None
    subject: str | None = None
    vendor_email: str | None = None
    added_at: str | None = None


class MSAEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    direction: str
    from_addr: str
    to_addr: str
    subject: str
    body: str
    attachment_name: str | None
    attachment_storage_key: str | None = None
    gmail_message_id: str | None = None
    version_id: int | None = None
    sent_at: datetime
    sent_by_id: int | None


class MSAOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    vendor_name: str
    vendor_email: str
    contract_type: str
    deal_reference: str | None
    status: str
    risk_score: float | None
    current_version: int
    redlined_text: str | None
    ai_suggestions: list | None
    template_id: int | None = None
    canonical_version_id: int | None = None
    executed_version_id: int | None = None
    gmail_thread_id: str | None
    gmail_auto_ingest: bool = True
    assigned_to_id: int | None
    review_guidelines: str | None = None
    change_history: list | None = None
    created_at: datetime
    updated_at: datetime
    emails: list[MSAEmailOut] = []
    my_access_level: str | None = None
    shares: list[MSAShareOut] = []
    risk_breakdown: MSARiskBreakdown | None = None


class MSASummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vendor_name: str
    contract_type: str
    status: str
    risk_score: float | None
    updated_at: datetime
    my_access_level: str | None = None
