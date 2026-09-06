from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class FormFieldSchema(BaseModel):
    id: str
    label: str
    type: str
    required: bool = True
    help_text: str | None = None
    placeholder: str | None = None
    options: list[str] | None = None


class FormSectionSchema(BaseModel):
    id: str
    title: str
    # Optional intro shown under the section title. Absent on every template
    # created before guidance existed, hence the default.
    description: str | None = None
    fields: list[FormFieldSchema] = Field(default_factory=list)


class RepeatableGroupSchema(BaseModel):
    id: str
    title: str
    description: str | None = None
    fields: list[FormFieldSchema] = Field(default_factory=list)


class FormTemplateSchema(BaseModel):
    # "How to fill this form" instructions, shown above the wizard and carried
    # into the exported workbook so an offline filler sees them too.
    description: str | None = None
    sections: list[FormSectionSchema] = Field(default_factory=list)
    repeatable_groups: list[RepeatableGroupSchema] = Field(default_factory=list)


class FormTemplateCreate(BaseModel):
    name: str
    schema: FormTemplateSchema


class FormTemplateUpdate(BaseModel):
    name: str | None = None
    schema: FormTemplateSchema | None = None
    is_active: bool | None = None


class FormTemplateResponse(ORMBase):
    id: UUID
    name: str
    version: int
    schema: dict
    is_active: bool
    created_by: UUID | None
    created_at: datetime


class FormAssignmentCreate(BaseModel):
    template_id: UUID
    assignee_id: UUID
    title: str
    due_at: datetime | None = None
    vendor_id: UUID | None = None
    vendor_name: str | None = None


class FormAssignmentItemCreate(BaseModel):
    assignee_id: UUID
    vendor_id: UUID | None = None
    vendor_name: str | None = None


class FormAssignmentBulkCreate(BaseModel):
    template_id: UUID
    title: str
    due_at: datetime | None = None
    assignments: list[FormAssignmentItemCreate]


class ExcelSheetPreview(BaseModel):
    index: int
    name: str
    row_count: int


class ExcelImportPreviewResponse(BaseModel):
    sheets: list[ExcelSheetPreview]


class FormAssignmentDraftUpdate(BaseModel):
    answers: dict[str, str | list[dict[str, str]]]


class FormAssignmentSubmit(BaseModel):
    answers: dict[str, str | list[dict[str, str]]]


class FormSubmissionResponse(ORMBase):
    id: UUID
    assignment_id: UUID
    answers: dict
    submitted_by: UUID
    submitted_at: datetime


class FormAssignmentResponse(ORMBase):
    id: UUID
    template_id: UUID
    assignee_id: UUID
    assigned_by_id: UUID
    vendor_id: UUID | None
    vendor_legal_name: str | None = None
    assignee_display_name: str | None = None
    classification_job_id: UUID | None
    # Status/outcome of the M1 classification kicked off at submit, so the UI
    # can show progress without polling the classification endpoint per row.
    classification_status: str | None = None
    classification_label: str | None = None
    title: str
    due_at: datetime | None
    status: str
    draft_answers: dict | None
    last_reminder_at: datetime | None
    created_at: datetime
    updated_at: datetime
    template: FormTemplateResponse | None = None
    submission: FormSubmissionResponse | None = None


class FormImportResultResponse(BaseModel):
    """Outcome of importing a filled workbook back into an assignment's draft."""

    assignment: FormAssignmentResponse
    imported_count: int
    unmatched: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
