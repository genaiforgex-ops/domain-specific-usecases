"""UC-06 Legal News & Regulatory Monitoring."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone

from app.api.deps import client_ip, require_permission, session_id
from app.core.rbac import Permission, Role
from app.database import get_db
from app.models.news import RegulatoryUpdate
from app.models.tracked_source import TrackedSource
from app.models.user import User
from app.schemas.news import (
    DiscoverResult,
    DiscoverSaveRequest,
    NewsIngest,
    NewsOut,
    NewsOverview,
    NewsTriage,
    RefreshSummary,
    TrackedSourceCreate,
    TrackedSourceOut,
    TrackedSourceUpdate,
)
from app.orchestrator import tasks as orch_tasks
from app.services import news_service
from app.services.audit_service import write_audit
from sqlalchemy import func, or_


router = APIRouter(prefix="/api/legal-news", tags=["legal-news"])

_FULL = Permission.LEGAL_NEWS_FULL
_ANY = (Permission.LEGAL_NEWS_FULL, Permission.LEGAL_NEWS_DIGEST)


@router.get("", response_model=list[NewsOut])
def list_updates(
    user: User = Depends(require_permission(*_ANY)),
    db: Session = Depends(get_db),
    source: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    regulator: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3650),
) -> list[NewsOut]:
    stmt = select(RegulatoryUpdate).order_by(RegulatoryUpdate.published_at.desc())
    if source or regulator:
        stmt = stmt.where(RegulatoryUpdate.source == (source or regulator))
    if status_filter:
        stmt = stmt.where(RegulatoryUpdate.status == status_filter)
    if category:
        stmt = stmt.where(RegulatoryUpdate.category == category)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(RegulatoryUpdate.title.ilike(like), RegulatoryUpdate.summary.ilike(like)))
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(RegulatoryUpdate.published_at >= cutoff)
    rows = db.execute(stmt).scalars().all()
    # Read-only roles only see top-relevance digest items.
    if user.role == Role.READ_ONLY.value:
        rows = [r for r in rows if r.relevance_score >= 0.5 or r.status == "action_required"]
    return [NewsOut.model_validate(r) for r in rows]


@router.get("/overview", response_model=NewsOverview)
def overview(
    _: User = Depends(require_permission(*_ANY)),
    db: Session = Depends(get_db),
) -> NewsOverview:
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    total = db.execute(select(func.count(RegulatoryUpdate.id))).scalar_one()
    action = db.execute(
        select(func.count(RegulatoryUpdate.id)).where(RegulatoryUpdate.status == "action_required")
    ).scalar_one()
    this_week = db.execute(
        select(func.count(RegulatoryUpdate.id)).where(RegulatoryUpdate.ingested_at >= week_ago)
    ).scalar_one()
    sources_count = db.execute(
        select(func.count(TrackedSource.id)).where(TrackedSource.enabled.is_(True))
    ).scalar_one()
    last_refreshed = db.execute(select(func.max(TrackedSource.last_fetched_at))).scalar_one()
    return NewsOverview(
        total=int(total),
        action_required=int(action),
        new_this_week=int(this_week),
        sources_count=int(sources_count),
        last_refreshed=last_refreshed,
    )


# ── Tracked sources ────────────────────────────────────────────────────────────


@router.get("/sources", response_model=list[TrackedSourceOut])
def list_sources(
    _: User = Depends(require_permission(*_ANY)),
    db: Session = Depends(get_db),
) -> list[TrackedSourceOut]:
    rows = db.execute(select(TrackedSource).order_by(TrackedSource.id)).scalars().all()
    return [TrackedSourceOut.model_validate(r) for r in rows]


@router.post("/sources", response_model=TrackedSourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: TrackedSourceCreate,
    user: User = Depends(require_permission(_FULL)),
    db: Session = Depends(get_db),
) -> TrackedSourceOut:
    url = payload.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL must start with http:// or https://")
    dup = db.execute(select(TrackedSource).where(TrackedSource.url == url)).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This source is already tracked")
    src = TrackedSource(
        name=payload.name.strip() or url,
        url=url,
        regulator=payload.regulator,
        category=payload.category,
        source_type=payload.source_type if payload.source_type in ("web", "rss") else "web",
        added_by_id=user.id,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return TrackedSourceOut.model_validate(src)


@router.patch("/sources/{source_id}", response_model=TrackedSourceOut)
def update_source(
    source_id: int,
    payload: TrackedSourceUpdate,
    _: User = Depends(require_permission(_FULL)),
    db: Session = Depends(get_db),
) -> TrackedSourceOut:
    src = db.get(TrackedSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(src, field, value)
    db.commit()
    db.refresh(src)
    return TrackedSourceOut.model_validate(src)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: int,
    _: User = Depends(require_permission(_FULL)),
    db: Session = Depends(get_db),
):
    from fastapi import Response

    src = db.get(TrackedSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    db.delete(src)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Refresh (scrape) & discover ───────────────────────────────────────────────


@router.post("/refresh", response_model=RefreshSummary)
def refresh_all(
    _: User = Depends(require_permission(_FULL)),
    db: Session = Depends(get_db),
) -> RefreshSummary:
    return RefreshSummary(**news_service.scrape_all(db))


@router.post("/sources/{source_id}/refresh", response_model=RefreshSummary)
def refresh_one(
    source_id: int,
    _: User = Depends(require_permission(_FULL)),
    db: Session = Depends(get_db),
) -> RefreshSummary:
    if db.get(TrackedSource, source_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return RefreshSummary(**news_service.scrape_all(db, only_source_id=source_id))


@router.get("/discover", response_model=list[DiscoverResult])
def discover(
    q: str = Query(min_length=2),
    _: User = Depends(require_permission(_FULL)),
) -> list[DiscoverResult]:
    return [DiscoverResult(**r) for r in news_service.discover(q)]


@router.post("/discover/save", response_model=NewsOut, status_code=status.HTTP_201_CREATED)
def save_discovered(
    payload: DiscoverSaveRequest,
    request: Request,
    user: User = Depends(require_permission(_FULL)),
    db: Session = Depends(get_db),
) -> NewsOut:
    upd = news_service.save_discovered(
        db,
        url=payload.url,
        title=payload.title,
        regulator=payload.regulator,
        category=payload.category,
        user_id=user.id,
    )
    write_audit(
        db,
        user=user,
        action_type="news_saved",
        module="legal_news",
        input_summary=f"url={payload.url[:200]}",
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=upd.id,
    )
    db.commit()
    db.refresh(upd)
    return NewsOut.model_validate(upd)


@router.post("/ingest", response_model=NewsOut, status_code=status.HTTP_201_CREATED)
def ingest_update(
    payload: NewsIngest,
    request: Request,
    user: User = Depends(require_permission(Permission.LEGAL_NEWS_FULL)),
    db: Session = Depends(get_db),
) -> NewsOut:
    """Manual ingest hook. Production replaces this with scheduled scrapers."""
    analysis = orch_tasks.analyse_regulatory_update(
        payload.source,
        payload.title,
        payload.full_text,
        module="legal_news",
        operation="analyse_regulatory_update",
        user_id=user.id,
        db=db,
    )
    upd = RegulatoryUpdate(
        source=payload.source,
        title=payload.title,
        summary=analysis.summary,
        full_text=payload.full_text,
        url=payload.url,
        tags=analysis.tags,
        relevance_score=analysis.relevance_score,
        status="for_information",
        published_at=payload.published_at,
    )
    db.add(upd)
    db.flush()
    write_audit(
        db,
        user=user,
        action_type="news_ingested",
        module="legal_news",
        input_summary=f"source={payload.source} title={payload.title[:120]}",
        ai_output_summary=analysis.summary[:500],
        confidence_score=analysis.relevance_score,
        model_version=analysis.model_version,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=upd.id,
        extra={"tags": analysis.tags},
    )
    db.commit()
    db.refresh(upd)
    return NewsOut.model_validate(upd)


@router.post("/{update_id}/triage", response_model=NewsOut)
def triage_update(
    update_id: int,
    payload: NewsTriage,
    request: Request,
    user: User = Depends(require_permission(Permission.LEGAL_NEWS_FULL)),
    db: Session = Depends(get_db),
) -> NewsOut:
    if payload.status not in {"action_required", "for_information", "not_relevant"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid triage status")
    upd = db.get(RegulatoryUpdate, update_id)
    if upd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Update not found")
    upd.status = payload.status
    upd.impact_note = payload.impact_note
    upd.triaged_by_id = user.id
    write_audit(
        db,
        user=user,
        action_type="news_triaged",
        module="legal_news",
        input_summary=f"update_id={update_id}",
        human_decision=payload.status,
        ip_address=client_ip(request),
        session_id=session_id(request),
        target_id=update_id,
    )
    db.commit()
    db.refresh(upd)
    return NewsOut.model_validate(upd)
