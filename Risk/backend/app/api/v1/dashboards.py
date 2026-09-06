from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("/operational")
async def operational_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = DashboardService(db)
    return await svc.operational_metrics()


@router.get("/risk-trends")
async def risk_trends(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = DashboardService(db)
    return await svc.risk_trends()
