"""Admin oversight — cross-pipeline aggregates for the Admin dashboard.

Read-only rollups over briefs, copies, banner images and the event trail:
pipeline funnel, pending work by role, estimated AI spend, throughput and a
recent-activity feed. No mutation happens here.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.ai_call import AiCall
from app.models.brief import Brief, BriefStage, BriefStatus
from app.models.brief_event import BriefEvent, BriefEventKind
from app.models.creative import Creative
from app.schemas.admin import (
    AdminBriefRow,
    AdminOverview,
    AiCallItem,
    Costing,
    CostingBrief,
    CostingDetail,
    CostingModel,
    CostingOp,
    CostingOpDetail,
    CostingTotals,
    CostingWindows,
    FilterOptions,
    OperationTrendPoint,
    PendingItem,
    PendingWork,
    StageCounts,
    StatusCounts,
    Throughput,
    TrendPoint,
)
from app.services import pricing

_RECENT_LIMIT = 12
_OLDEST_LIMIT = 6
_BRIEFS_LIMIT = 200

_OPEN_STAGES = [
    BriefStage.brief_review.value,
    BriefStage.copywriting.value,
    BriefStage.design.value,
    BriefStage.creative_review.value,
    BriefStage.final_signoff.value,
]


@dataclass
class OverviewFilters:
    """The dashboard's date-range + entity filters. All optional; unset means
    'no constraint on this dimension'."""

    start: datetime | None = None
    end: datetime | None = None
    status: str | None = None
    product: str | None = None
    user_id: uuid.UUID | None = None


def _title(brief: Brief) -> str:
    return brief.project_name or brief.product_name or "Untitled brief"


def _involves_user(user_id: uuid.UUID):
    """A brief 'involves' a user if they authored it or hold any stage slot."""
    return or_(
        Brief.creator_id == user_id,
        Brief.copywriter_id == user_id,
        Brief.marketing_id == user_id,
        Brief.product_id == user_id,
        Brief.designer_id == user_id,
    )


def _brief_scope(f: OverviewFilters) -> list:
    """Non-date brief predicates (status / product / user) shared by every
    brief-based aggregate.

    NOTE: this is reused by the AiCall path (see _ai_scope/_ai_query), which only
    joins Brief when an entity filter is set — so it must NOT add an unconditional
    Brief predicate. Soft-delete exclusion is applied separately, on the pure-Brief
    ``scope`` in build_overview and build_briefs, where Brief is always present.
    """
    preds = []
    if f.status:
        preds.append(Brief.status == f.status)
    if f.product:
        preds.append(Brief.product_name == f.product)
    if f.user_id:
        preds.append(_involves_user(f.user_id))
    return preds


def _created_range(f: OverviewFilters) -> list:
    """Date-range applied to when the brief was created (pipeline / pending)."""
    preds = []
    if f.start:
        preds.append(Brief.created_at >= f.start)
    if f.end:
        preds.append(Brief.created_at <= f.end)
    return preds


def _export_range(f: OverviewFilters) -> list:
    """Date-range applied to when the brief shipped (throughput)."""
    preds = []
    if f.start:
        preds.append(Brief.figma_exported_at >= f.start)
    if f.end:
        preds.append(Brief.figma_exported_at <= f.end)
    return preds


def _ai_needs_brief(f: OverviewFilters) -> bool:
    return bool(f.product or f.user_id or f.status)


def _ai_scope(f: OverviewFilters) -> list:
    """Predicates for AiCall queries. status==ok always; date-range on the call;
    product/user/status via a Brief join (see _ai_needs_brief)."""
    preds = [AiCall.status == "ok"]
    if f.start:
        preds.append(AiCall.created_at >= f.start)
    if f.end:
        preds.append(AiCall.created_at <= f.end)
    preds.extend(_brief_scope(f))
    return preds


def _ai_query(columns, f: OverviewFilters):
    stmt = select(*columns)
    if _ai_needs_brief(f):
        stmt = stmt.join(Brief, AiCall.brief_id == Brief.id)
    return stmt.where(*_ai_scope(f))


def _count_by(db: Session, column, preds: list) -> dict[str, int]:
    rows = db.execute(
        select(column, func.count()).where(*preds).group_by(column)
    ).all()
    return {key: n for key, n in rows}


def _scalar(db: Session, stmt) -> int:
    return db.execute(stmt).scalar_one() or 0


def build_overview(db: Session, filters: OverviewFilters | None = None) -> AdminOverview:
    f = filters or OverviewFilters()
    # Pure-Brief queries below always reference Brief, so exclude soft-deleted here.
    scope = _brief_scope(f) + [Brief.deleted_at.is_(None)]
    created = _created_range(f)
    stage = _count_by(db, Brief.stage, scope + created)
    status = _count_by(db, Brief.status, scope + created)

    totals = StageCounts(
        draft=stage.get(BriefStage.draft.value, 0),
        brief_review=stage.get(BriefStage.brief_review.value, 0),
        copywriting=stage.get(BriefStage.copywriting.value, 0),
        design=stage.get(BriefStage.design.value, 0),
        creative_review=stage.get(BriefStage.creative_review.value, 0),
        final_signoff=stage.get(BriefStage.final_signoff.value, 0),
        completed=stage.get(BriefStage.completed.value, 0),
    )
    by_status = StatusCounts(
        draft=status.get(BriefStatus.draft.value, 0),
        submitted=status.get(BriefStatus.submitted.value, 0),
        approved=status.get(BriefStatus.approved.value, 0),
        changes_requested=status.get(BriefStatus.changes_requested.value, 0),
    )

    # ── Pending work, by who it's waiting on ────────────────────────────────
    copywriting_total = totals.copywriting
    with_copies = select(Creative.brief_id).distinct().subquery()
    awaiting_copy = _scalar(
        db,
        select(func.count())
        .select_from(Brief)
        .where(
            Brief.stage == BriefStage.copywriting.value,
            Brief.id.notin_(select(with_copies.c.brief_id)),
            *scope,
            *created,
        ),
    )

    def stage_total(stage_value: str) -> int:
        return _scalar(
            db,
            select(func.count()).select_from(Brief).where(
                Brief.stage == stage_value, *scope, *created
            ),
        )

    design_total = _scalar(
        db,
        select(func.count()).select_from(Brief).where(
            Brief.stage == BriefStage.design.value,
            Brief.figma_exported_at.is_(None),
            *scope,
            *created,
        ),
    )

    pending = PendingWork(
        brief_review_total=stage_total(BriefStage.brief_review.value),
        awaiting_copy=awaiting_copy,
        copywriting_total=copywriting_total,
        design_total=design_total,
        creative_review_total=stage_total(BriefStage.creative_review.value),
        final_signoff_total=stage_total(BriefStage.final_signoff.value),
    )

    # ── Costing — real AI spend from logged token usage on every call ───────
    op_rows = db.execute(
        _ai_query(
            [
                AiCall.operation,
                func.count(),
                func.coalesce(func.sum(AiCall.input_tokens), 0),
                func.coalesce(func.sum(AiCall.output_tokens), 0),
                func.coalesce(func.sum(AiCall.total_tokens), 0),
                func.coalesce(func.avg(AiCall.latency_ms), 0),
                func.coalesce(func.sum(AiCall.cost_inr), 0.0),
            ],
            f,
        ).group_by(AiCall.operation)
    ).all()
    by_operation = [
        CostingOp(
            operation=op,
            calls=calls,
            input_tokens=int(inp),
            output_tokens=int(out),
            total_tokens=int(tot),
            avg_latency_ms=int(lat),
            cost_inr=round(float(cost), 4),
        )
        for op, calls, inp, out, tot, lat, cost in op_rows
    ]
    costing = Costing(
        total_calls=sum(o.calls for o in by_operation),
        input_tokens=sum(o.input_tokens for o in by_operation),
        output_tokens=sum(o.output_tokens for o in by_operation),
        total_tokens=sum(o.total_tokens for o in by_operation),
        estimated_inr=round(sum(o.cost_inr for o in by_operation), 2),
        avg_latency_ms=(
            int(sum(o.avg_latency_ms * o.calls for o in by_operation) / sum(o.calls for o in by_operation))
            if by_operation
            else 0
        ),
        by_operation=by_operation,
    )

    # ── Throughput ──────────────────────────────────────────────────────────
    exported = _scalar(
        db,
        select(func.count()).select_from(Brief).where(
            Brief.figma_exported_at.isnot(None), *scope, *_export_range(f)
        ),
    )
    # A bounce = a change request, on the brief (legacy) or any approval lane.
    # Scope to the filtered briefs via a join when entity filters are set; the
    # date-range applies to when the bounce happened (BriefEvent.at).
    cr_stmt = select(func.count()).select_from(BriefEvent)
    if _ai_needs_brief(f):
        cr_stmt = cr_stmt.join(Brief, BriefEvent.brief_id == Brief.id).where(*scope)
    if f.start:
        cr_stmt = cr_stmt.where(BriefEvent.at >= f.start)
    if f.end:
        cr_stmt = cr_stmt.where(BriefEvent.at <= f.end)
    change_requests = _scalar(
        db,
        cr_stmt.where(
            (BriefEvent.kind == BriefEventKind.changes_requested.value)
            | (
                (BriefEvent.kind == BriefEventKind.gate1_signoff.value)
                & BriefEvent.note.isnot(None)
            )
        ),
    )
    shipped = db.execute(
        select(Brief.created_at, Brief.figma_exported_at).where(
            Brief.figma_exported_at.isnot(None), *scope, *_export_range(f)
        )
    ).all()
    avg_lead_time_hours: float | None = None
    if shipped:
        hours = [(exp - created_at).total_seconds() / 3600 for created_at, exp in shipped]
        avg_lead_time_hours = round(sum(hours) / len(hours), 1)
    throughput = Throughput(
        exported=exported,
        change_requests=change_requests,
        avg_lead_time_hours=avg_lead_time_hours,
    )

    # ── Oldest pending (bottlenecks) ────────────────────────────────────────
    now = datetime.now(timezone.utc)
    open_briefs = db.execute(
        select(Brief)
        .where(
            Brief.stage.in_(_OPEN_STAGES),
            Brief.figma_exported_at.is_(None),
            *scope,
            *created,
        )
        .order_by(Brief.updated_at.asc())
        .limit(_OLDEST_LIMIT)
    ).scalars()
    oldest_pending = [
        PendingItem(
            id=b.id,
            title=_title(b),
            stage=b.stage,
            waiting_days=max(0, (now - b.updated_at).days),
            updated_at=b.updated_at,
        )
        for b in open_briefs
    ]

    # ── Trend series (spend + throughput over time) — always daily buckets ──
    spend_bucket = func.date_trunc("day", AiCall.created_at)
    spend_rows = db.execute(
        _ai_query([spend_bucket, func.coalesce(func.sum(AiCall.cost_inr), 0.0)], f)
        .group_by(spend_bucket)
        .order_by(spend_bucket)
    ).all()
    spend_trend = [
        TrendPoint(bucket=b.date(), value=round(float(v), 2)) for b, v in spend_rows if b
    ]

    tp_bucket = func.date_trunc("day", Brief.figma_exported_at)
    tp_rows = db.execute(
        select(tp_bucket, func.count())
        .where(Brief.figma_exported_at.isnot(None), *scope, *_export_range(f))
        .group_by(tp_bucket)
        .order_by(tp_bucket)
    ).all()
    throughput_trend = [
        TrendPoint(bucket=b.date(), value=float(n)) for b, n in tp_rows if b
    ]

    # ── Filter options (all products; users come from the account directory) ──
    product_rows = db.execute(
        select(Brief.product_name)
        .where(Brief.product_name.isnot(None))
        .distinct()
        .order_by(Brief.product_name)
    ).scalars()
    filter_options = FilterOptions(products=[p for p in product_rows if p])

    return AdminOverview(
        totals=totals,
        by_status=by_status,
        pending=pending,
        costing=costing,
        throughput=throughput,
        oldest_pending=oldest_pending,
        spend_trend=spend_trend,
        throughput_trend=throughput_trend,
        filter_options=filter_options,
    )


def build_briefs(
    db: Session,
    filters: OverviewFilters | None = None,
    *,
    stage: str | None = None,
    exported: bool | None = None,
    sort: str = "waiting",
) -> list[AdminBriefRow]:
    """The filtered brief list the dashboard KPI cards / bars deep-link into.

    `stage` accepts a concrete stage or the sentinel 'open' (any non-terminal
    stage). `sort` is 'waiting' (oldest-touched first) or 'recent'."""
    f = filters or OverviewFilters()
    preds = _brief_scope(f) + _created_range(f) + [Brief.deleted_at.is_(None)]
    if stage == "open":
        preds.append(Brief.stage.in_(_OPEN_STAGES))
    elif stage:
        preds.append(Brief.stage == stage)
    if exported is True:
        preds.append(Brief.figma_exported_at.isnot(None))
    elif exported is False:
        preds.append(Brief.figma_exported_at.is_(None))

    order = Brief.updated_at.asc() if sort == "waiting" else Brief.updated_at.desc()
    rows = db.execute(
        select(Brief).where(*preds).order_by(order).limit(_BRIEFS_LIMIT)
    ).scalars()
    now = datetime.now(timezone.utc)
    return [
        AdminBriefRow(
            id=b.id,
            title=_title(b),
            stage=b.stage,
            status=b.status,
            product=b.product_name,
            waiting_days=max(0, (now - b.updated_at).days),
            updated_at=b.updated_at,
            exported=b.figma_exported_at is not None,
        )
        for b in rows
    ]


def _spend_since(db: Session, ts: datetime | None) -> float:
    stmt = select(func.coalesce(func.sum(AiCall.cost_inr), 0.0)).where(AiCall.status == "ok")
    if ts is not None:
        stmt = stmt.where(AiCall.created_at >= ts)
    return float(db.execute(stmt).scalar_one() or 0.0)


def build_costing(db: Session) -> CostingDetail:
    """Granular AI-spend breakdown: by operation (with input/output split), by
    model, by brief, plus spend windows and the recent-call feed."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = CostingWindows(
        today_inr=round(_spend_since(db, today), 2),
        week_inr=round(_spend_since(db, now - timedelta(days=7)), 2),
        total_inr=round(_spend_since(db, None), 2),
    )

    # Daily spend buckets over all traced calls — the "spend over time" chart.
    trend_bucket = func.date_trunc("day", AiCall.created_at)
    trend_rows = db.execute(
        select(trend_bucket, func.coalesce(func.sum(AiCall.cost_inr), 0.0))
        .where(AiCall.status == "ok")
        .group_by(trend_bucket)
        .order_by(trend_bucket)
    ).all()
    spend_trend = [
        TrendPoint(bucket=b.date(), value=round(float(v), 2)) for b, v in trend_rows if b
    ]

    # Same daily buckets, split by operation — the "spend by operation over time" chart.
    op_trend_rows = db.execute(
        select(trend_bucket, AiCall.operation, func.coalesce(func.sum(AiCall.cost_inr), 0.0))
        .where(AiCall.status == "ok")
        .group_by(trend_bucket, AiCall.operation)
        .order_by(trend_bucket)
    ).all()
    spend_by_operation_trend = [
        OperationTrendPoint(bucket=b.date(), operation=op, value=round(float(v), 2))
        for b, op, v in op_trend_rows if b
    ]

    # One pass grouped by (operation, model) — lets us split cost by lane while
    # rolling up to both per-operation and per-model views.
    rows = db.execute(
        select(
            AiCall.operation,
            AiCall.model,
            func.count(),
            func.coalesce(func.sum(AiCall.input_tokens), 0),
            func.coalesce(func.sum(AiCall.output_tokens), 0),
            func.coalesce(func.sum(AiCall.cost_inr), 0.0),
            func.coalesce(func.avg(AiCall.latency_ms), 0),
        )
        .where(AiCall.status == "ok")
        .group_by(AiCall.operation, AiCall.model)
    ).all()

    ops: dict[str, dict] = {}
    models: dict[str, dict] = {}
    for operation, model, calls, inp, out, cost, lat in rows:
        inp, out, cost, calls = int(inp), int(out), float(cost), int(calls)
        in_inr, out_inr = pricing.split_cost_inr(model, inp, out)
        op = ops.setdefault(
            operation,
            {"calls": 0, "in": 0, "out": 0, "in_inr": 0.0, "out_inr": 0.0, "cost": 0.0, "latw": 0.0},
        )
        for key, val in (("calls", calls), ("in", inp), ("out", out), ("in_inr", in_inr),
                         ("out_inr", out_inr), ("cost", cost), ("latw", float(lat) * calls)):
            op[key] += val
        m = models.setdefault(model, {"calls": 0, "in": 0, "out": 0, "cost": 0.0})
        for key, val in (("calls", calls), ("in", inp), ("out", out), ("cost", cost)):
            m[key] += val

    by_operation = sorted(
        (
            CostingOpDetail(
                operation=k,
                calls=v["calls"],
                input_tokens=v["in"],
                output_tokens=v["out"],
                input_cost_inr=round(v["in_inr"], 4),
                output_cost_inr=round(v["out_inr"], 4),
                cost_inr=round(v["cost"], 4),
                avg_latency_ms=int(v["latw"] / v["calls"]) if v["calls"] else 0,
            )
            for k, v in ops.items()
        ),
        key=lambda o: o.cost_inr,
        reverse=True,
    )
    by_model = sorted(
        (
            CostingModel(
                model=k,
                calls=v["calls"],
                input_tokens=v["in"],
                output_tokens=v["out"],
                cost_inr=round(v["cost"], 4),
            )
            for k, v in models.items()
        ),
        key=lambda m: m.cost_inr,
        reverse=True,
    )

    totals = CostingTotals(
        calls=sum(o.calls for o in by_operation),
        input_tokens=sum(o.input_tokens for o in by_operation),
        output_tokens=sum(o.output_tokens for o in by_operation),
        total_tokens=sum(o.input_tokens + o.output_tokens for o in by_operation),
        cost_inr=round(sum(o.cost_inr for o in by_operation), 2),
        avg_latency_ms=(
            int(sum(o.avg_latency_ms * o.calls for o in by_operation) / sum(o.calls for o in by_operation))
            if by_operation
            else 0
        ),
    )

    # ── By brief — top spenders ─────────────────────────────────────────────
    brief_rows = db.execute(
        select(
            AiCall.brief_id,
            func.count(),
            func.coalesce(func.sum(AiCall.total_tokens), 0),
            func.coalesce(func.sum(AiCall.cost_inr), 0.0),
        )
        .where(AiCall.status == "ok", AiCall.brief_id.isnot(None))
        .group_by(AiCall.brief_id)
        .order_by(func.sum(AiCall.cost_inr).desc())
        .limit(_OLDEST_LIMIT)
    ).all()
    brief_ids = [bid for bid, *_ in brief_rows]
    titles: dict[int, str] = {}
    if brief_ids:
        for b in db.execute(select(Brief).where(Brief.id.in_(brief_ids))).scalars():
            titles[b.id] = _title(b)
    by_brief = [
        CostingBrief(
            brief_id=bid,
            title=titles.get(bid, f"Brief #{bid}"),
            calls=int(calls),
            total_tokens=int(tok),
            cost_inr=round(float(cost), 4),
        )
        for bid, calls, tok, cost in brief_rows
    ]

    # ── Recent calls feed ───────────────────────────────────────────────────
    calls_rows = db.execute(
        select(AiCall).order_by(AiCall.created_at.desc()).limit(_RECENT_LIMIT * 2)
    ).scalars()
    recent_calls = [
        AiCallItem(
            id=c.id,
            operation=c.operation,
            model=c.model,
            brief_id=c.brief_id,
            input_tokens=c.input_tokens,
            output_tokens=c.output_tokens,
            total_tokens=c.total_tokens,
            latency_ms=c.latency_ms,
            cost_inr=round(c.cost_inr, 4),
            status=c.status,
            at=c.created_at,
        )
        for c in calls_rows
    ]

    return CostingDetail(
        windows=windows,
        totals=totals,
        spend_trend=spend_trend,
        spend_by_operation_trend=spend_by_operation_trend,
        by_operation=by_operation,
        by_model=by_model,
        by_brief=by_brief,
        recent_calls=recent_calls,
    )
