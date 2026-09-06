"""Admin metrics aggregations for governance dashboards."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import Date, cast, func, or_, select, union_all
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.comparison import DocumentComparison
from app.models.contract import Contract
from app.models.llm_usage import LLMUsageLog
from app.models.msa_version import MSADocumentVersion
from app.models.query import LegalBotQuery
from app.models.user import User
from app.schemas.metrics import (
    DailyCountOut,
    DailyTokenOut,
    MetricsSummaryOut,
    MetricsUserRowOut,
    MetricsUsersPageOut,
    ModuleDailyOut,
    ModuleUsageOut,
    UserSegmentOut,
)

AI_ACTION_TYPES = {
    "contract_reviewed",
    "contract_rereview",
    "documents_compared",
    "legal_bot_query",
    "research_drafted",
    "news_ingested",
    "msa_started",
    "msa_ai_review_run",
    "msa_vendor_review",
    "prompt_edit_proposed",
    "msa_prompt_edit_proposed",
    "task_created",
    "tasks_extracted",
}

MODULE_LABELS: dict[str, str] = {
    "legal_bot": "LegalBot",
    "contract_review": "Contract Review",
    "document_comparison": "Document Comparison",
    "legal_research": "Legal Research",
    "msa_automation": "MSA Automation",
    "legal_news": "Legal News",
    "tasks": "Task Manager",
    "auth": "Auth",
}

USER_SEGMENTS = [
    ("power", "Power Users", "> 25 Queries", 26, None),
    ("regular", "Regular Users", "11 - 25 Queries", 11, 25),
    ("occasional", "Occasional Users", "1 - 10 Queries", 1, 10),
    ("inactive", "Inactive Users", "0 Queries", 0, 0),
]


def segment_for_query_count(count: int) -> str:
    if count > 25:
        return "power"
    if count >= 11:
        return "regular"
    if count >= 1:
        return "occasional"
    return "inactive"


def parse_date_range(
    start_date: date | None,
    end_date: date | None,
    *,
    default_days: int = 30,
) -> tuple[datetime, datetime]:
    """UTC day boundaries inclusive of end_date."""
    if end_date is None:
        end_day = datetime.now(timezone.utc).date()
    else:
        end_day = end_date
    if start_date is None:
        start_day = end_day - timedelta(days=default_days - 1)
    else:
        start_day = start_date
    start_dt = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_day, time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def _day_expr(column: Any) -> Any:
    """Truncate a timestamp to UTC calendar day (PostgreSQL-safe for GROUP BY)."""
    return cast(column, Date)


def _daily_counts(
    db: Session,
    column: Any,
    *where_clauses: Any,
) -> list[DailyCountOut]:
    day = _day_expr(column)
    rows = db.execute(
        select(day, func.count())
        .where(*where_clauses)
        .group_by(day)
        .order_by(day)
    ).all()
    return [DailyCountOut(day=row[0], count=int(row[1])) for row in rows]


def get_summary(db: Session, start_dt: datetime, end_dt: datetime) -> MetricsSummaryOut:
    total_users = db.scalar(select(func.count()).select_from(User)) or 0

    active_from_audit = (
        db.scalar(
            select(func.count(func.distinct(AuditLog.user_id))).where(
                AuditLog.timestamp >= start_dt,
                AuditLog.timestamp <= end_dt,
                AuditLog.user_id.is_not(None),
            )
        )
        or 0
    )
    active_from_usage = (
        db.scalar(
            select(func.count(func.distinct(LLMUsageLog.user_id))).where(
                LLMUsageLog.timestamp >= start_dt,
                LLMUsageLog.timestamp <= end_dt,
                LLMUsageLog.user_id.is_not(None),
            )
        )
        or 0
    )
    active_users = max(active_from_audit, active_from_usage)

    contracts = _count_in_range(db, Contract.created_at, start_dt, end_dt)
    msa_versions = _count_in_range(db, MSADocumentVersion.created_at, start_dt, end_dt)
    comparisons = _count_in_range(db, DocumentComparison.created_at, start_dt, end_dt)
    total_documents = contracts + msa_versions + comparisons

    total_queries = (
        _count_in_range(db, LegalBotQuery.created_at, start_dt, end_dt)
    )

    token_row = db.execute(
        select(
            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
        ).where(
            LLMUsageLog.timestamp >= start_dt,
            LLMUsageLog.timestamp <= end_dt,
        )
    ).one()
    input_tokens = int(token_row[0])
    output_tokens = int(token_row[1])
    total_tokens = int(token_row[2])

    ai_actions = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.timestamp >= start_dt,
                AuditLog.timestamp <= end_dt,
                AuditLog.action_type.in_(AI_ACTION_TYPES),
            )
        )
        or 0
    )

    return MetricsSummaryOut(
        total_users=total_users,
        active_users=active_users,
        total_documents=total_documents,
        total_queries=total_queries,
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        ai_actions=ai_actions,
    )


def _count_in_range(db: Session, column: Any, start_dt: datetime, end_dt: datetime) -> int:
    return int(
        db.scalar(
            select(func.count()).where(column >= start_dt, column <= end_dt)
        )
        or 0
    )


def get_login_activity(db: Session, start_dt: datetime, end_dt: datetime) -> list[DailyCountOut]:
    return _daily_counts(
        db,
        AuditLog.timestamp,
        AuditLog.action_type == "login",
        AuditLog.timestamp >= start_dt,
        AuditLog.timestamp <= end_dt,
    )


def get_usage_trend(db: Session, start_dt: datetime, end_dt: datetime) -> list[ModuleDailyOut]:
    day = _day_expr(AuditLog.timestamp)
    rows = db.execute(
        select(day, AuditLog.module, func.count())
        .where(
            AuditLog.timestamp >= start_dt,
            AuditLog.timestamp <= end_dt,
            AuditLog.action_type.in_(AI_ACTION_TYPES),
        )
        .group_by(day, AuditLog.module)
        .order_by(day, AuditLog.module)
    ).all()
    return [ModuleDailyOut(day=row[0], module=row[1], count=int(row[2])) for row in rows]


def _documents_daily_subq(column: Any, start_dt: datetime, end_dt: datetime):
    day = _day_expr(column)
    return (
        select(day.label("day"), func.count().label("count"))
        .where(column >= start_dt, column <= end_dt)
        .group_by(day)
    )


def get_documents_trend(db: Session, start_dt: datetime, end_dt: datetime) -> list[DailyCountOut]:
    combined = union_all(
        _documents_daily_subq(Contract.created_at, start_dt, end_dt),
        _documents_daily_subq(MSADocumentVersion.created_at, start_dt, end_dt),
        _documents_daily_subq(DocumentComparison.created_at, start_dt, end_dt),
    ).subquery()
    rows = db.execute(
        select(combined.c.day, func.sum(combined.c.count))
        .group_by(combined.c.day)
        .order_by(combined.c.day)
    ).all()
    return [DailyCountOut(day=row[0], count=int(row[1])) for row in rows]


def get_token_trend(db: Session, start_dt: datetime, end_dt: datetime) -> list[DailyTokenOut]:
    day = _day_expr(LLMUsageLog.timestamp)
    rows = db.execute(
        select(
            day,
            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
        )
        .where(LLMUsageLog.timestamp >= start_dt, LLMUsageLog.timestamp <= end_dt)
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        DailyTokenOut(
            day=row[0],
            input_tokens=int(row[1]),
            output_tokens=int(row[2]),
            total_tokens=int(row[3]),
        )
        for row in rows
    ]


def get_user_segments(db: Session, start_dt: datetime, end_dt: datetime) -> list[UserSegmentOut]:
    query_counts = dict(
        db.execute(
            select(LegalBotQuery.user_id, func.count())
            .where(
                LegalBotQuery.created_at >= start_dt,
                LegalBotQuery.created_at <= end_dt,
            )
            .group_by(LegalBotQuery.user_id)
        ).all()
    )
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    if total_users == 0:
        return []

    buckets = {key: 0 for key, *_ in USER_SEGMENTS}
    users_with_queries = set(query_counts.keys())
    for _uid, count in query_counts.items():
        buckets[segment_for_query_count(count)] += 1
    buckets["inactive"] = total_users - len(users_with_queries)

    return [
        UserSegmentOut(
            segment=key,
            label=label,
            query_range=query_range,
            count=buckets[key],
            percentage=round((buckets[key] / total_users) * 100, 1),
        )
        for key, label, query_range, _min, _max in USER_SEGMENTS
    ]


def get_module_usage(db: Session, start_dt: datetime, end_dt: datetime) -> list[ModuleUsageOut]:
    rows = db.execute(
        select(AuditLog.module, func.count())
        .where(
            AuditLog.timestamp >= start_dt,
            AuditLog.timestamp <= end_dt,
            AuditLog.action_type.in_(AI_ACTION_TYPES),
        )
        .group_by(AuditLog.module)
        .order_by(func.count().desc())
    ).all()
    return [
        ModuleUsageOut(module=row[0], label=MODULE_LABELS.get(row[0], row[0]), count=int(row[1]))
        for row in rows
    ]


def _user_documents_subq(start_dt: datetime, end_dt: datetime):
    contracts = select(
        Contract.uploaded_by_id.label("user_id"),
        func.count().label("documents"),
    ).where(Contract.created_at >= start_dt, Contract.created_at <= end_dt).group_by(
        Contract.uploaded_by_id
    )
    msa = select(
        MSADocumentVersion.created_by_id.label("user_id"),
        func.count().label("documents"),
    ).where(
        MSADocumentVersion.created_at >= start_dt,
        MSADocumentVersion.created_at <= end_dt,
        MSADocumentVersion.created_by_id.is_not(None),
    ).group_by(MSADocumentVersion.created_by_id)
    comparisons = select(
        DocumentComparison.created_by_id.label("user_id"),
        func.count().label("documents"),
    ).where(
        DocumentComparison.created_at >= start_dt,
        DocumentComparison.created_at <= end_dt,
    ).group_by(DocumentComparison.created_by_id)
    combined = union_all(contracts, msa, comparisons).subquery()
    return (
        select(combined.c.user_id, func.sum(combined.c.documents).label("documents"))
        .group_by(combined.c.user_id)
        .subquery()
    )


def _user_tokens_subq(start_dt: datetime, end_dt: datetime):
    return (
        select(
            LLMUsageLog.user_id,
            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("total_tokens"),
        )
        .where(
            LLMUsageLog.timestamp >= start_dt,
            LLMUsageLog.timestamp <= end_dt,
            LLMUsageLog.user_id.is_not(None),
        )
        .group_by(LLMUsageLog.user_id)
        .subquery()
    )


def _user_queries_subq(start_dt: datetime, end_dt: datetime):
    return (
        select(
            LegalBotQuery.user_id,
            func.count().label("queries"),
        )
        .where(LegalBotQuery.created_at >= start_dt, LegalBotQuery.created_at <= end_dt)
        .group_by(LegalBotQuery.user_id)
        .subquery()
    )


def get_users_page(
    db: Session,
    start_dt: datetime,
    end_dt: datetime,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> MetricsUsersPageOut:
    docs = _user_documents_subq(start_dt, end_dt)
    queries = _user_queries_subq(start_dt, end_dt)
    tokens = _user_tokens_subq(start_dt, end_dt)

    stmt = (
        select(
            User.id,
            User.email,
            User.full_name,
            User.role,
            User.last_login_at,
            func.coalesce(docs.c.documents, 0),
            func.coalesce(queries.c.queries, 0),
            func.coalesce(tokens.c.input_tokens, 0),
            func.coalesce(tokens.c.output_tokens, 0),
            func.coalesce(tokens.c.total_tokens, 0),
        )
        .outerjoin(docs, docs.c.user_id == User.id)
        .outerjoin(queries, queries.c.user_id == User.id)
        .outerjoin(tokens, tokens.c.user_id == User.id)
        .order_by(User.email)
    )
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(like),
                func.lower(User.full_name).like(like),
            )
        )

    count_stmt = select(func.count()).select_from(User)
    if search:
        like = f"%{search.strip().lower()}%"
        count_stmt = count_stmt.where(
            or_(
                func.lower(User.email).like(like),
                func.lower(User.full_name).like(like),
            )
        )
    total = db.scalar(count_stmt) or 0
    offset = max(0, (page - 1) * page_size)
    rows = db.execute(stmt.offset(offset).limit(page_size)).all()

    items = [
        MetricsUserRowOut(
            user_id=row[0],
            email=row[1],
            full_name=row[2],
            role=row[3],
            last_login_at=row[4],
            documents=int(row[5]),
            queries=int(row[6]),
            input_tokens=int(row[7]),
            output_tokens=int(row[8]),
            total_tokens=int(row[9]),
        )
        for row in rows
    ]
    return MetricsUsersPageOut(items=items, total=int(total), page=page, page_size=page_size)


def get_chat_feedback_summary(
    db: Session, start_dt: datetime, end_dt: datetime
) -> dict[str, Any]:
    """Thumbs / comments on LawGenie turns for the metrics panel."""
    from app.models.chat import ChatTurn

    rows = (
        db.execute(
            select(ChatTurn)
            .where(
                ChatTurn.created_at >= start_dt,
                ChatTurn.created_at <= end_dt,
                or_(ChatTurn.feedback.is_not(None), ChatTurn.feedback_comment.is_not(None)),
            )
            .order_by(ChatTurn.id.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    up = sum(1 for t in rows if t.feedback == 1)
    down = sum(1 for t in rows if t.feedback == -1)
    commented = sum(1 for t in rows if t.feedback_comment)
    recent = [
        {
            "turn_id": t.id,
            "mode": t.mode,
            "feedback": {1: "up", -1: "down"}.get(t.feedback) if t.feedback else None,
            "comment": (t.feedback_comment or "")[:240] or None,
            "query": (t.user_query or "")[:120],
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows[:12]
    ]
    return {
        "up": up,
        "down": down,
        "commented": commented,
        "total_rated": up + down,
        "recent": recent,
    }


def export_users_csv(
    db: Session,
    start_dt: datetime,
    end_dt: datetime,
    *,
    search: str | None = None,
) -> str:
    page = get_users_page(
        db, start_dt, end_dt, search=search, page=1, page_size=10_000
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Email",
            "Name",
            "Role",
            "Documents",
            "Queries",
            "Input Tokens",
            "Output Tokens",
            "Total Tokens",
            "Last Login",
        ]
    )
    for row in page.items:
        writer.writerow(
            [
                row.email,
                row.full_name,
                row.role,
                row.documents,
                row.queries,
                row.input_tokens,
                row.output_tokens,
                row.total_tokens,
                row.last_login_at.isoformat() if row.last_login_at else "",
            ]
        )
    return buf.getvalue()
