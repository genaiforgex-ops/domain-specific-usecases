"""Schemas for the Prompt Studio — per-user hero-image art-direction per template."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ImagePromptOut(BaseModel):
    """One image use-case (a banner template) as the current user sees it: the
    built-in default art-direction, their editable prompt, and whether a custom
    override is in effect."""

    template_id: UUID
    template_name: str
    size_names: list[str]
    default_prompt: str  # the template's built-in art-direction (reset target)
    prompt: str  # what to show in the editor (override text, or the default)
    is_custom: bool  # the user has saved an override
    enabled: bool  # the override is active (only meaningful when is_custom)
    image_aspect: str  # output aspect ratio for this format ("" = model default)
    image_size: str  # output resolution tier ("1K"/"2K"/"4K"; "" = model default)
    updated_at: datetime | None = None


class ImagePromptUpdate(BaseModel):
    """Save a user's art-direction override for a template."""

    prompt: str = Field(min_length=1, max_length=4000)
    enabled: bool = True


class DesignPromptOut(BaseModel):
    """The shared design-prompt base as the current user sees it: the built-in
    default, their editable override, and whether a custom base is in effect."""

    default_prompt: str  # the built-in brand scaffold (reset target)
    prompt: str  # what to show in the editor (override text, or the default)
    is_custom: bool
    enabled: bool
    updated_at: datetime | None = None


class DesignPromptUpdate(BaseModel):
    """Save the user's design-prompt base override."""

    prompt: str = Field(min_length=1, max_length=8000)
    enabled: bool = True
