import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.project import Project, RiskScore
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    RiskScoreResponse,
    ScoreOverride,
    WhatIfRequest,
)
from app.services.scoring_service import ScoringService

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:read")),
):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:create")),
):
    project = Project(
        name=body.name,
        business_line=body.business_line,
        vendor_id=body.vendor_id,
        intake_data=body.intake_data,
        created_by=user.id,
    )
    db.add(project)
    await db.flush()
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:read")),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/projects/{project_id}/score", response_model=RiskScoreResponse)
async def compute_score(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:create")),
):
    svc = ScoringService(db)
    return await svc.compute_score(project_id, user.id)


@router.post("/projects/{project_id}/what-if")
async def what_if_score(
    project_id: uuid.UUID,
    body: WhatIfRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:read")),
):
    svc = ScoringService(db)
    return await svc.what_if(project_id, body.control_outcomes)


@router.post("/risk-scores/{score_id}/override", response_model=RiskScoreResponse)
async def override_score(
    score_id: uuid.UUID,
    body: ScoreOverride,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:override")),
):
    svc = ScoringService(db)
    try:
        return await svc.override_score(
            score_id, body.inherent_score, body.residual_score, body.justification, user.id
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/projects/{project_id}/scores", response_model=list[RiskScoreResponse])
async def list_project_scores(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("m3:read")),
):
    result = await db.execute(
        select(RiskScore).where(RiskScore.project_id == project_id).order_by(RiskScore.created_at.desc())
    )
    return result.scalars().all()
