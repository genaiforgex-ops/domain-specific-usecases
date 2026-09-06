from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracker_id: int
    version_number: int
    source: str
    filename: str | None
    mime_type: str | None
    storage_key: str | None
    parent_version_id: int | None
    comparison_id: int | None
    created_by_id: int | None
    gmail_message_id: str | None
    created_at: datetime
    download_url: str | None = None


class NegotiationChangeItemOut(BaseModel):
    diff_index: int
    title: str
    old_text: str
    new_text: str
    severity: str
    impact: str
    suggested_action: str


class NegotiationChangesOut(BaseModel):
    comparison_id: int | None
    summary_report: str | None
    executive_summary: str | None
    diff_blocks: list[dict]
    risk_commentary: list[dict]
    llm_narrative: list[NegotiationChangeItemOut]
    from_version_number: int | None = None
    to_version_number: int | None = None


class NegotiationTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracker_id: int
    version_id: int | None
    comparison_id: int | None
    diff_index: int | None
    title: str
    description: str
    suggested_action: str | None
    severity: str
    status: str
    assigned_to_id: int | None
    due_date: datetime | None = None
    promoted_task_id: int | None = None
    resolved_at: datetime | None
    created_at: datetime


class NegotiationTaskUpdate(BaseModel):
    status: str | None = None
    assigned_to_id: int | None = None


class MSAStartRequest(BaseModel):
    vendor_name: str
    vendor_email: EmailStr
    contract_type: str = "MSA"
    deal_reference: str | None = None
    template_id: int | None = None
    base_text: str | None = None
    review_guidelines: str | None = None
    skip_ai_review: bool = False


# ── Prompt-based document editing (UC-05) ──────────────────────────────────────


class MSAPromptEditRequest(BaseModel):
    instruction: str
    selection: str | None = None
    base_version_id: int | None = None
    review_guidelines: str | None = None


class MSAEditChangeOut(BaseModel):
    description: str
    original: str
    revised: str


class MSADocxOperationOut(BaseModel):
    op_type: str
    anchor_id: str | None = None
    after_anchor_id: str | None = None
    target_text: str | None = None
    content: str | None = None
    description: str
    confidence: float = 0.8


class MSADocxOperationResultOut(BaseModel):
    op_index: int
    op_type: str
    description: str
    status: str
    message: str = ""


class MSADiffBlockOut(BaseModel):
    kind: str  # equal | insert | delete | replace
    v1: str
    v2: str


class MSAPromptEditPreview(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    revision_id: int | None = None
    base_version_id: int
    base_version_number: int
    base_text: str
    edited_text: str
    change_summary: str | None
    changes: list[MSAEditChangeOut] = []
    operations: list[MSADocxOperationOut] = []
    operation_results: list[MSADocxOperationResultOut] = []
    edit_mode: str = "text"
    structure_hash: str | None = None
    diff_blocks: list[MSADiffBlockOut] = []
    model_version: str | None
    ai_fallback: bool = False


class MSAPromptEditApply(BaseModel):
    instruction: str
    edited_text: str = ""
    parent_version_id: int
    revision_id: int | None = None
    # Optional curated DOCX ops — when set, replaces the revision's planned ops
    # before apply so reviewers can fix AI wording without opening OnlyOffice.
    operations: list[MSADocxOperationOut] | None = None


class MSAPromptRevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracker_id: int
    base_version_id: int
    instruction: str
    change_summary: str | None
    edit_mode: str
    status: str
    model_version: str | None
    created_at: datetime
    applied_at: datetime | None


class MSAPromptRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracker_id: int
    base_version_id: int
    instruction: str
    selection: str | None
    base_text: str
    edited_text: str
    change_summary: str | None
    operations: list[MSADocxOperationOut] = []
    operation_results: list[MSADocxOperationResultOut] = []
    structure_hash: str | None
    edit_mode: str
    diff_blocks: list[MSADiffBlockOut] = []
    status: str
    model_version: str | None
    resulting_version_id: int | None
    created_at: datetime
    applied_at: datetime | None


class MSASuggestionsPreview(BaseModel):
    base_version_id: int
    base_version_number: int
    base_text: str
    edited_text: str
    diff_blocks: list[MSADiffBlockOut] = []
    applied_count: int
    blocked_count: int
    accepted_count: int
    applied: list[dict] = []
    blocked: list[dict] = []


class MSASuggestionsApply(BaseModel):
    parent_version_id: int
    edited_text: str = ""
    force: bool = False
    change_mode: str = "track"


class MSAHumanEditApply(BaseModel):
    parent_version_id: int
    edited_text: str
    rich_html: str | None = None


class OnlyOfficeConfigOut(BaseModel):
    document_server_url: str
    token: str
    config: dict
    enabled: bool = True


class OnlyOfficeForcesaveOut(BaseModel):
    accepted: bool
    error_code: int
