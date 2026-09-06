"""Schemas for the Prompt Studio's text-agent side — per-user prompt appends."""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentPromptOut(BaseModel):
    """One pipeline agent as the current user sees it: its identity, base prompt
    (read-only, for the graph), the user's append, and whether it is active."""

    kind: str
    name: str
    role: str
    description: str
    stage: str
    base_prompt: str  # the brand-governed base instruction (shown, not editable)
    output_label: str
    append: str  # the user's appended instruction ("" when none)
    is_custom: bool  # the user has saved an append
    enabled: bool  # the append is active
    updated_at: datetime | None = None


class AgentPromptUpdate(BaseModel):
    """Save a user's append for an agent."""

    prompt: str = Field(min_length=1, max_length=6000)
    enabled: bool = True
