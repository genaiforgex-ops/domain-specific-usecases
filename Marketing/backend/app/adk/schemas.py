"""Pydantic output schemas for the ADK agents.

The Brief Creator extraction schema is built dynamically from the shared field
catalog so its structured output always matches the brief columns. The Creative
Agent uses a fixed schema describing one ad creative in the standard format.
"""

from functools import lru_cache

from pydantic import BaseModel, Field, create_model

from app.services.brief_fields import fields_for


@lru_cache
def extraction_schema(brief_type: str) -> type[BaseModel]:
    catalog = fields_for(brief_type)
    field_defs = {
        key: (str | None, Field(default=None, description=label)) for key, label in catalog
    }
    name = f"{'Large' if brief_type == 'large' else 'SmallMedium'}BriefExtract"
    return create_model(name, **field_defs)


class CreativeDraft(BaseModel):
    """One ad creative in the standard format."""

    visual_reference: str = Field(
        description=(
            "A verbose, cinematic art-direction brief for the hero photograph — "
            "3-6 rich sentences, not a one-liner. Describe, in order: the Indian "
            "subject(s) and their age/role; clothing with specific colours; their "
            "pose, gaze and action; any phone or device held naturally within the "
            "scene (present but never the hero); the setting and background; the "
            "natural light, time of day and weather; the camera framing and "
            "composition (eye-level, medium shot / close-up / environmental "
            "portrait); the emotional mood; and a premium photorealistic film "
            "finish. People first, technology second. No text, logos or UI in the "
            "scene — the banner adds those later."
        )
    )
    headline: str = Field(description="8-9 words, ~55 characters, max 2-3 lines.")
    body: str = Field(description="Body copy: 10-12 words, ~72 characters, max 2-3 lines.")
    cta: str = Field(description="A short call to action, e.g. 'Buy Now', 'Invest Now'.")
    entity_attribution: str | None = Field(
        default=None,
        description="Optional value attribution line, e.g. 'Members save more'.",
    )
    terms: str | None = Field(default=None, description="Terms line, e.g. '*T&Cs apply'.")


class CreativeSet(BaseModel):
    """The set of creatives the agent produces for a brief."""

    creatives: list[CreativeDraft] = Field(description="The generated creatives.")
