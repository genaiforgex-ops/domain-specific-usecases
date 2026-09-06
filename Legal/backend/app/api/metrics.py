"""Admin metrics API — governance dashboards."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.rbac import Permission
from app.database import get_db
from app.models.user import User
from app.schemas.metrics import (
    ChatFeedbackSummaryOut,
    DailyCountOut,
    DailyTokenOut,
    MetricsSummaryOut,
    MetricsUsersPageOut,
    ModuleDailyOut,
    ModuleUsageOut,
    UserSegmentOut,
)
from app.services import metrics_service as svc


router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummaryOut)
def metrics_summary(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> MetricsSummaryOut:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_summary(db, start_dt, end_dt)


@router.get("/login-activity", response_model=list[DailyCountOut])
def login_activity(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[DailyCountOut]:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_login_activity(db, start_dt, end_dt)


@router.get("/usage-trend", response_model=list[ModuleDailyOut])
def usage_trend(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[ModuleDailyOut]:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_usage_trend(db, start_dt, end_dt)


@router.get("/documents-trend", response_model=list[DailyCountOut])
def documents_trend(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[DailyCountOut]:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_documents_trend(db, start_dt, end_dt)


@router.get("/token-trend", response_model=list[DailyTokenOut])
def token_trend(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[DailyTokenOut]:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_token_trend(db, start_dt, end_dt)


@router.get("/user-segments", response_model=list[UserSegmentOut])
def user_segments(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[UserSegmentOut]:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_user_segments(db, start_dt, end_dt)


@router.get("/module-usage", response_model=list[ModuleUsageOut])
def module_usage(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[ModuleUsageOut]:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_module_usage(db, start_dt, end_dt)


@router.get("/users", response_model=MetricsUsersPageOut)
def metrics_users(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MetricsUsersPageOut:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return svc.get_users_page(
        db, start_dt, end_dt, search=search, page=page, page_size=page_size
    )


@router.get("/chat-feedback", response_model=ChatFeedbackSummaryOut)
def chat_feedback(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> ChatFeedbackSummaryOut:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    return ChatFeedbackSummaryOut(**svc.get_chat_feedback_summary(db, start_dt, end_dt))


@router.get("/users/export")
def export_users(
    _: User = Depends(require_permission(Permission.AUDIT_LOG_ALL)),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    search: str | None = Query(default=None),
) -> PlainTextResponse:
    start_dt, end_dt = svc.parse_date_range(start_date, end_date)
    csv_text = svc.export_users_csv(db, start_dt, end_dt, search=search)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="metrics-users.csv"'},
    )
