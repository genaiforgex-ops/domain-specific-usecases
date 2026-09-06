from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.services.metrics_service import MetricsService, cutoff_for

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
async def summary(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return await MetricsService(db).summary(cutoff_for(range_days))


@router.get("/activity")
async def activity(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return {"points": await MetricsService(db).login_activity(cutoff_for(range_days))}


@router.get("/token-trend")
async def token_trend(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return {"points": await MetricsService(db).token_trend(cutoff_for(range_days))}


@router.get("/features")
async def features(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return await MetricsService(db).feature_stats(cutoff_for(range_days))


@router.get("/users")
async def users(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return {"users": await MetricsService(db).per_user(cutoff_for(range_days))}


@router.get("/agents")
async def agents(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return {"agents": await MetricsService(db).per_agent(cutoff_for(range_days))}


@router.get("/vendors")
async def vendors(
    range_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("metrics:read")),
):
    return {"vendors": await MetricsService(db).per_vendor(cutoff_for(range_days))}
