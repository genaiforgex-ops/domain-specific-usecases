"""AgentPrompt — a user's custom instruction appended to a pipeline agent's prompt.

The Prompt Studio's text-agent side (the image side lives in ImagePrompt). Each row
is one (user, agent_kind) pairing holding extra instruction text that is appended to
that agent's brand-governed base prompt at run time. The base prompt is never
replaced — the append is added under a clear header (see agents._compose) — so a
user can steer an agent without discarding the brand rules. `agent_kind` matches the
keys in `app.adk.agents.AGENTS` (e.g. "brief_creator", "creative").
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentPrompt(Base):
    __tablename__ = "agent_prompts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    agent_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Extra instruction appended to the agent's base prompt.
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # A user can keep an append on file but toggle it off (falls back to base only).
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
