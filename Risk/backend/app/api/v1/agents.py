import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentDefaults, AgentResponse, AgentUpdate
from app.services.agent_service import AgentService

router = APIRouter(prefix="/m1/agents", tags=["m1-agents"])


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    return await AgentService(db).list_agents(active_only=True)


@router.get("/defaults", response_model=AgentDefaults)
async def get_agent_defaults(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    """Built-in guidance/model/temperature, used to prefill the editor so a new
    agent starts from exactly today's behavior."""
    return AgentService(db).get_default_prompts()


@router.post("", response_model=AgentResponse)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:agent_manage")),
):
    return await AgentService(db).create_agent(body.model_dump(), user.id)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:read")),
):
    try:
        return await AgentService(db).get_agent(agent_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m1:agent_manage")),
):
    # exclude_unset so PATCH only writes the fields the client actually sent.
    try:
        return await AgentService(db).update_agent(agent_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
