"""Brief DTOs — intake content, create/update bodies, output, and review action."""

import uuid

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.brief import BriefType


class BriefContent(BaseModel):
    """All editable fields. Every field is optional so drafts can be partial;
    required-on-submit rules live in the service, keyed by brief_type.

    Note: assignees are NOT here — work auto-routes to admin-configured default
    accounts (see assignment_service); users don't pick who gets a brief."""

    # Downstream production default — the banner *category* the Product Lead picks
    # at brief creation (locks which template family the Designer works from;
    # nullable → older briefs fall back to every template).
    banner_category: str | None = None

    # Shared identity. The two dates are absent on purpose: they're system-owned
    # (brief_date = the day it was raised, expected_date = +3 days) and derived by
    # brief_service.stamp_dates on every save, so there is nothing for a client to
    # send. They're returned on BriefOut.
    project_name: str | None = None
    product_name: str | None = None
    owner_name: str | None = None

    # Small / Medium template
    sm_go_live_timeline: str | None = None
    sm_one_line_summary: str | None = None
    sm_primary_goal: str | None = None
    sm_business_kpi: str | None = None
    sm_strategic_context: str | None = None
    sm_audience_who: str | None = None
    sm_audience_segment: str | None = None
    sm_audience_exclusions: str | None = None
    sm_mandatories_tnc: str | None = None
    sm_platforms: str | None = None
    sm_dimensions_specs: str | None = None
    sm_final_ui_screen: str | None = None
    sm_samples_references: str | None = None

    # Large template
    lg_project_purpose: str | None = None
    lg_business_objective: str | None = None
    lg_marketing_objective: str | None = None
    lg_communication_objective: str | None = None
    lg_effectiveness_metric: str | None = None
    lg_ideal_customer: str | None = None
    lg_demo_age: str | None = None
    lg_demo_gender: str | None = None
    lg_demo_top_cities: str | None = None
    lg_goals_motivations: str | None = None
    lg_category_insight: str | None = None
    lg_conservative_target: str | None = None
    lg_aspirational_target: str | None = None
    lg_product_insight: str | None = None
    lg_key_markets: str | None = None
    lg_competition: str | None = None
    lg_product_features: str | None = None
    lg_key_features_deliverables: str | None = None
    lg_unique_offerings: str | None = None
    lg_think_before: str | None = None
    lg_think_after: str | None = None
    lg_feel_before: str | None = None
    lg_feel_after: str | None = None
    lg_do_before: str | None = None
    lg_do_after: str | None = None
    lg_cultural_sensitivity: str | None = None
    lg_languages: str | None = None
    lg_other_considerations: str | None = None
    lg_deliverables: str | None = None


class BriefReferenceImageOut(BaseModel):
    """One sample/example image attached to a brief (bytes excluded — the browser
    fetches them from the content endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brief_id: uuid.UUID
    filename: str
    caption: str | None
    mime_type: str
    uploaded_by_id: uuid.UUID | None
    uploaded_by_name: str
    created_at: datetime


class BriefCreate(BriefContent):
    brief_type: BriefType


class BriefUpdate(BriefContent):
    pass  # all fields optional; brief_type is fixed after creation


class BriefSummary(BaseModel):  # list view
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brief_type: str
    status: str
    stage: str
    project_name: str | None
    product_name: str | None
    owner_name: str | None
    budget_inr: int | None
    submitted_at: datetime | None
    updated_at: datetime


class BriefOut(BriefContent):  # full detail — reads from the ORM object
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brief_type: str
    status: str
    stage: str
    creator_id: uuid.UUID

    # System-owned dates — read-only: the day the brief was raised and, three days
    # on, when it's expected back. See brief_service.stamp_dates.
    brief_date: date | None
    expected_date: date | None

    review_note: str | None
    reviewer_id: uuid.UUID | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Task allocation — assignees work auto-routed to (kept for display; set by
    # the system from the role defaults, not by users).
    copywriter_id: uuid.UUID | None
    marketing_id: uuid.UUID | None
    product_id: uuid.UUID | None
    designer_id: uuid.UUID | None

    # Campaign budget (display only).
    budget_inr: int | None

    # Approval checkpoints (brief review + creative review by ML, final sign-off by PL)
    brief_review_state: str
    creative_review_state: str
    final_signoff_state: str
    brief_review_by_id: uuid.UUID | None
    creative_review_by_id: uuid.UUID | None
    final_signoff_by_id: uuid.UUID | None
    brief_review_at: datetime | None
    creative_review_at: datetime | None
    final_signoff_at: datetime | None

    # The banner template the Designer picked inside the brief's category — set
    # before the hero images are generated, and reused by the Figma export.
    banner_template_id: uuid.UUID | None

    # This brief's own copy direction (the individual-level copy prompt). Written
    # by the author / a Product Lead through its own route, not the content PATCH.
    copy_prompt: str | None

    # Figma export (Designer)
    figma_file_key: str | None
    figma_file_url: str | None
    figma_exported_at: datetime | None

    # Sample/example images attached to the brief (metadata only).
    reference_images: list[BriefReferenceImageOut] = []


class CopyPromptUpdate(BaseModel):
    """This brief's copy direction — the individual-level copy prompt. Blank clears
    it, so the master (Prompt Studio) prompts run on their own."""

    prompt: str | None = None


class ApprovalRequest(BaseModel):
    """An approval checkpoint decision. The checkpoint (brief review / creative
    review / final sign-off) is derived from the brief's current stage, not the body."""

    action: Literal["approve", "request_changes"]
    note: str | None = None  # required by the service when requesting changes


class RejectRequest(BaseModel):
    """A work-stage owner sending the brief back a step for changes. The target
    stage is derived from the brief's current stage; the note (the reason) is
    required so whoever it lands on knows what to fix."""

    note: str


ReassignSlot = Literal[
    "author", "marketing_brief", "copywriter", "designer", "marketing_creative", "product"
]


class ReassignRequest(BaseModel):
    """Hand a brief's current-stage task to another active user of the same role.

    `slot` says which assignee to change; when omitted it's derived from the
    caller's role and the brief's stage (e.g. a Copywriter at the copywriting
    stage reassigns the `copywriter` slot). Admins must name the slot explicitly."""

    assignee_id: uuid.UUID
    slot: ReassignSlot | None = None
    note: str | None = None


class BriefExtractRequest(BaseModel):
    brief_type: BriefType
    raw_text: str


class BriefExtractResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    values: dict[str, str]  # column key -> extracted value
    model_version: str


class BriefEventOut(BaseModel):  # one entry in the immutable audit trail
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brief_id: uuid.UUID
    kind: str
    action: str
    actor_id: uuid.UUID | None
    actor_name: str
    actor_role: str
    note: str | None
    at: datetime
    # Set in the router so the audit page can label which brief an entry belongs to.
    brief_title: str | None = None


class BriefInboxItem(BaseModel):
    """A brief that needs the creator's action now — drives the BC Inbox."""

    id: uuid.UUID
    brief_type: str
    stage: str  # pipeline position — drives the step dots in the inbox table
    status: str
    title: str
    cta: str
    priority: Literal["high", "normal"]
    review_note: str | None
    updated_at: datetime
