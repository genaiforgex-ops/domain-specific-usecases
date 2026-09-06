"""Admin routes — the read-only cross-pipeline oversight dashboard, plus the
default-assignee levers (which account new work auto-routes to per role)."""

import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin import (
    AdminBriefRow,
    AdminOverview,
    CostingDetail,
    RoleDefaultOut,
    RoleDefaultSet,
)
from app.services import admin_service, assignment_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _filters(
    start: date | None,
    end: date | None,
    status: str | None,
    product: str | None,
    user_id: uuid.UUID | None,
) -> admin_service.OverviewFilters:
    """Build the service filter object from the dashboard query params. Dates are
    widened to cover the whole day, in UTC."""
    return admin_service.OverviewFilters(
        start=datetime.combine(start, time.min, tzinfo=timezone.utc) if start else None,
        end=datetime.combine(end, time.max, tzinfo=timezone.utc) if end else None,
        status=status or None,
        product=product or None,
        user_id=user_id,
    )


def _role_default_out(role: str, user: User | None) -> RoleDefaultOut:
    return RoleDefaultOut(
        role=role,
        role_label=assignment_service.ROLE_LABELS.get(role, role),
        user_id=user.id if user else None,
        full_name=user.full_name if user else None,
    )


@router.get("/role-defaults", response_model=list[RoleDefaultOut])
def list_role_defaults(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[RoleDefaultOut]:
    """The default account new work auto-routes to for each role."""
    defaults = assignment_service.list_defaults(db)
    return [_role_default_out(role, defaults[role]) for role in assignment_service.ASSIGNABLE_ROLES]


@router.put("/role-defaults/{role}", response_model=RoleDefaultOut)
def set_role_default(
    role: str,
    payload: RoleDefaultSet,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> RoleDefaultOut:
    """Set the default account for a role. The user must be active and hold it."""
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        assignment_service.set_default(db, role, user)
    except assignment_service.DefaultAssigneeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.commit()
    return _role_default_out(role, user)


@router.get("/overview", response_model=AdminOverview)
def overview(
    start: date | None = Query(None),
    end: date | None = Query(None),
    status: str | None = Query(None),
    product: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminOverview:
    """Aggregated pipeline, pending-work, costing and throughput rollups, scoped
    by the optional date-range / status / product / user filters."""
    return admin_service.build_overview(db, _filters(start, end, status, product, user_id))


@router.get("/briefs", response_model=list[AdminBriefRow])
def briefs(
    start: date | None = Query(None),
    end: date | None = Query(None),
    status: str | None = Query(None),
    product: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    stage: str | None = Query(None),
    exported: bool | None = Query(None),
    sort: str = Query("waiting"),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[AdminBriefRow]:
    """The filtered brief list the dashboard KPI cards / bars deep-link into."""
    return admin_service.build_briefs(
        db,
        _filters(start, end, status, product, user_id),
        stage=stage or None,
        exported=exported,
        sort=sort,
    )


@router.get("/costing", response_model=CostingDetail)
def costing(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> CostingDetail:
    """Granular AI-spend breakdown — by operation, model, brief, plus call feed."""
    return admin_service.build_costing(db)
