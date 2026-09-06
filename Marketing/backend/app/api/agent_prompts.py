"""Prompt Studio routes (text agents) — a user's own instruction appends per agent.

Symmetric to image_prompts. Every authenticated user manages only their OWN appends
(keyed by user + agent_kind). Listing returns one entry per pipeline agent with its
base prompt folded in; PUT saves an append; DELETE resets an agent to base only.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.agent_prompt import AgentPromptOut, AgentPromptUpdate
from app.services import agent_prompt_service
from app.services.agent_prompt_service import EffectiveAgentPrompt

router = APIRouter(prefix="/api/agent-prompts", tags=["agent-prompts"])


def _assert_can_edit(agent_kind: str, role: str | None) -> None:
    """Only a role that runs an agent may steer its prompt (see AGENTS.editors)."""
    if not agent_prompt_service.can_edit(agent_kind, role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role cannot edit this agent's prompt",
        )


def _out(e: EffectiveAgentPrompt) -> AgentPromptOut:
    return AgentPromptOut(
        kind=e.kind,
        name=e.meta["name"],
        role=e.meta["role"],
        description=e.meta["description"],
        stage=e.meta["stage"],
        base_prompt=e.meta["base_instruction"],
        output_label=e.meta["output_label"],
        append=e.append,
        is_custom=e.is_custom,
        enabled=e.enabled,
        updated_at=e.override.updated_at if e.override else None,
    )


@router.get("", response_model=list[AgentPromptOut])
def list_agent_prompts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentPromptOut]:
    """The current user's prompt append for the agents their role runs (pipeline order)."""
    return [_out(e) for e in agent_prompt_service.list_effective(db, user.id, user.role)]


@router.put("/{agent_kind}", response_model=AgentPromptOut)
def set_agent_prompt(
    agent_kind: str,
    payload: AgentPromptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentPromptOut:
    """Save the current user's append for an agent."""
    _assert_can_edit(agent_kind, user.role)
    try:
        e = agent_prompt_service.set_append(
            db, user.id, agent_kind, payload.prompt, payload.enabled
        )
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ex)) from ex
    return _out(e)


@router.delete("/{agent_kind}", response_model=AgentPromptOut)
def reset_agent_prompt(
    agent_kind: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentPromptOut:
    """Reset an agent back to its base prompt for the current user."""
    _assert_can_edit(agent_kind, user.role)
    try:
        e = agent_prompt_service.reset(db, user.id, agent_kind)
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ex)) from ex
    return _out(e)
