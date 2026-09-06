"""Prompt Studio — per-user instructions appended to the pipeline agents.

The text-agent counterpart to image_prompt_service. Each agent (see
`app.adk.agents.AGENTS`) has a brand-governed base prompt; a user may append their
own instruction, stored one row per (user, agent_kind). `resolve_append` is the hot
path the AI seam calls to get the enabled append text for a user + agent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adk.agents import AGENT_KIND_CREATIVE, AGENTS, AGENTS_BY_KIND
from app.models.agent_prompt import AgentPrompt


@dataclass(frozen=True)
class EffectiveAgentPrompt:
    """One agent as the current user sees it: its registry metadata (base prompt,
    identity) plus the user's append override if any."""

    meta: dict  # a row from app.adk.agents.AGENTS
    override: AgentPrompt | None

    @property
    def kind(self) -> str:
        return self.meta["kind"]

    @property
    def is_custom(self) -> bool:
        return self.override is not None

    @property
    def enabled(self) -> bool:
        return self.override.enabled if self.override else False

    @property
    def append(self) -> str:
        """The user's append text (empty string when they have none)."""
        return self.override.prompt if self.override else ""


def _get(db: Session, user_id: uuid.UUID, agent_kind: str) -> AgentPrompt | None:
    return db.get(AgentPrompt, {"user_id": user_id, "agent_kind": agent_kind})


def list_effective(
    db: Session, user_id: uuid.UUID, role: str | None = None
) -> list[EffectiveAgentPrompt]:
    """The pipeline agents the given role may steer, in pipeline order, with the
    user's append folded in. Each agent names its own editors (see AGENTS): a
    role steers only the agent it runs — the Product Lead the Brief Creator, the
    Copywriter the Copy Agent. Admin (and role=None) see all. The image generator
    lives on the design side (see image_prompt_service)."""
    agents = AGENTS if role in (None, "AD") else [a for a in AGENTS if role in a["editors"]]
    overrides = {
        o.agent_kind: o
        for o in db.scalars(select(AgentPrompt).where(AgentPrompt.user_id == user_id))
    }
    return [EffectiveAgentPrompt(meta=a, override=overrides.get(a["kind"])) for a in agents]


def can_edit(agent_kind: str, role: str | None) -> bool:
    """Whether `role` may steer `agent_kind`'s prompt. Admin (and role=None) may
    edit any; everyone else only the agents that name their role in `editors`."""
    meta = AGENTS_BY_KIND.get(agent_kind)
    if meta is None:
        return False
    return role in (None, "AD") or role in meta["editors"]


def set_append(
    db: Session, user_id: uuid.UUID, agent_kind: str, prompt: str, enabled: bool
) -> EffectiveAgentPrompt:
    """Create or update the user's append for an agent."""
    meta = AGENTS_BY_KIND.get(agent_kind)
    if meta is None:
        raise ValueError("Unknown agent")
    row = _get(db, user_id, agent_kind)
    if row is None:
        row = AgentPrompt(user_id=user_id, agent_kind=agent_kind)
        db.add(row)
    row.prompt = prompt
    row.enabled = enabled
    db.commit()
    return EffectiveAgentPrompt(meta=meta, override=row)


def reset(db: Session, user_id: uuid.UUID, agent_kind: str) -> EffectiveAgentPrompt:
    """Drop the user's append so only the agent's base prompt runs."""
    meta = AGENTS_BY_KIND.get(agent_kind)
    if meta is None:
        raise ValueError("Unknown agent")
    row = _get(db, user_id, agent_kind)
    if row is not None:
        db.delete(row)
        db.commit()
    return EffectiveAgentPrompt(meta=meta, override=None)


def resolve_append(db: Session, user_id: uuid.UUID, agent_kind: str) -> str:
    """The instruction to append when `user_id` runs `agent_kind`: their enabled
    append text, or "" (base prompt only)."""
    row = _get(db, user_id, agent_kind)
    if row is not None and row.enabled and row.prompt.strip():
        return row.prompt
    return ""


def resolve_copy_direction(
    db: Session, *, actor_id: uuid.UUID, brief_prompt: str | None
) -> str:
    """Everything appended to the Copy Agent's base prompt for one generation run.

    Copy is steered at two levels, widest first — so the narrowest direction is
    read last and wins where they disagree:

      * **master** — the Copywriter's standing Prompt Studio prompt for the Copy
        Agent (they run it). The Product Lead steers copy per-brief, not here.
      * **individual** — this brief's own copy direction (`Brief.copy_prompt`),
        written by its author.

    Returns "" when nothing is set, i.e. the brand base prompt runs alone.
    """
    sections: list[tuple[str, str]] = []

    def add(label: str, text: str | None) -> None:
        text = (text or "").strip()
        if text:
            sections.append((label, text))

    add("Standing direction from the Copywriter", resolve_append(db, actor_id, AGENT_KIND_CREATIVE))
    add("Direction for THIS brief (takes precedence over the above)", brief_prompt)

    return "\n\n".join(f"{label}:\n{text}" for label, text in sections)
