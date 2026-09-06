"""Banner DTOs — AI hero images and the Figma export request/result.

Image bytes are never serialized here; the browser fetches them from the content
endpoint. These carry only metadata and review state.
"""

import uuid

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BannerImageOut(BaseModel):
    """One creative's current hero image (metadata only)."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    creative_id: uuid.UUID
    brief_id: uuid.UUID
    status: str  # pending | approved
    model_version: str
    active_message_id: uuid.UUID | None = None  # the chat version currently selected as live
    updated_at: datetime


class BannerImageMessageOut(BaseModel):
    """One turn in the Designer's chat with a hero image (bytes excluded)."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    image_id: uuid.UUID
    comment: str | None  # null on the base/seed version
    model_version: str
    created_at: datetime


class BannerTemplateSelectRequest(BaseModel):
    """The Designer's banner-template pick for a brief — made before the hero images
    are generated, and reused by regeneration and the Figma export."""

    template_id: uuid.UUID


class BannerGenerateRequest(BaseModel):
    """Optional inputs when generating/regenerating hero images. `template_id` picks
    the banner template whose composition the photos are art-directed for; omitted,
    the brief's own pick (see BannerTemplateSelectRequest) is used."""

    template_id: uuid.UUID | None = None


class BannerCommentResult(BaseModel):
    """The refreshed image plus the chat turn that produced it."""

    image: BannerImageOut
    message: BannerImageMessageOut


class FigmaExportRequest(BaseModel):
    """The Designer-supplied name for the new Figma file, optionally the banner
    template to render with (defaults to the gallery's default template), and
    optionally the subset of ad sizes to export (defaults to all of the
    template's sizes)."""

    file_name: str = Field(min_length=1, max_length=120)
    template_id: uuid.UUID | None = None
    # Size names to export (e.g. ["square", "story"]); None/empty = all sizes.
    sizes: list[str] | None = None


class FigmaExportResult(BaseModel):
    """Where the banners landed."""

    file_key: str
    file_url: str
    creatives: int
    sizes: int
