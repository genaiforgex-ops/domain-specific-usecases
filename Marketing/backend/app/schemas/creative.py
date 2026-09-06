"""Creative DTOs — generated ad creatives and the generation request."""

import uuid

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreativeOut(BaseModel):
    """One generated creative in the standard format."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    brief_id: uuid.UUID
    position: int
    visual_reference: str | None
    headline: str
    body: str
    cta: str
    entity_attribution: str | None
    terms: str | None
    model_version: str
    active_version_id: uuid.UUID | None = None
    created_at: datetime


class CreativeEditOne(BaseModel):
    """A copywriter's edit to one creative — saved as a new version."""

    headline: str
    body: str
    cta: str = Field(max_length=120)
    visual_reference: str | None = None
    entity_attribution: str | None = None
    terms: str | None = None


class CreativeVersionOut(BaseModel):
    """One entry in a creative's version history."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    creative_id: uuid.UUID
    label: str
    visual_reference: str | None
    headline: str
    body: str
    cta: str
    entity_attribution: str | None
    terms: str | None
    editor_name: str | None
    model_version: str
    created_at: datetime
    # Set in the router — whether this version is the creative's live one.
    is_active: bool = False


class CreativeGenerateRequest(BaseModel):
    """How many creatives to generate. Bounded to keep a single call sane."""

    count: int = Field(default=6, ge=1, le=12)


class CreativeUpdate(BaseModel):
    """The Copywriter's edits to one generated creative, keyed by its id."""

    id: uuid.UUID
    headline: str
    body: str
    cta: str = Field(max_length=120)
    visual_reference: str | None = None
    entity_attribution: str | None = None
    terms: str | None = None


class DesignHandoffRequest(BaseModel):
    """Save the (possibly edited) creatives and hand the brief to the Designer.

    The Designer is NOT chosen here — it auto-routes to the admin-configured
    default (see assignment_service)."""

    creatives: list[CreativeUpdate] = Field(default_factory=list)


class GenerationQueueItem(BaseModel):
    """A Gate-1-cleared brief awaiting (or already having) creative generation."""

    id: uuid.UUID
    brief_type: str
    stage: str  # pipeline position — drives the step dots in the queue tables
    project_name: str | None
    product_name: str | None
    owner_name: str | None
    budget_inr: int | None
    creative_count: int
    updated_at: datetime


class DesignQueueItem(BaseModel):
    """A brief handed to the Designer, with its banner-production progress so the
    Designer's dashboard can tell not-started / in-progress / ready / shipped apart."""

    id: uuid.UUID
    brief_type: str
    stage: str  # pipeline position — drives the step dots in the queue tables
    project_name: str | None
    product_name: str | None
    owner_name: str | None
    budget_inr: int | None
    creative_count: int
    image_count: int  # hero images generated so far
    approved_count: int  # of those, how many the Designer has approved
    figma_file_url: str | None  # set once exported — the "shipped" signal
    figma_exported_at: datetime | None
    updated_at: datetime
