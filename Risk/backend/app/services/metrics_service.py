"""Aggregations for the Metrics panel.

Reads from existing tables plus llm_usage_logs. All queries are scoped to a time
window (cutoff) so the panel's range selector works. Read-only — never mutates.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.classification import ClassificationJob
from app.models.usage import LLMUsageLog
from app.models.user import User, UserRole
from app.models.vendor import DDReport, Vendor

MODULES = ["M1", "M2", "M3"]


def cutoff_for(range_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=range_days)


def _day(col):
    # Truncate a timestamp to a date string (YYYY-MM-DD) for grouping.
    return cast(func.date_trunc("day", col), String)


class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summary(self, cutoff: datetime) -> dict:
        total_users = await self.db.scalar(select(func.count()).select_from(User)) or 0
        active_users = (
            await self.db.scalar(
                select(func.count()).select_from(User).where(User.last_login >= cutoff)
            )
            or 0
        )
        documents = (
            await self.db.scalar(
                select(func.count()).select_from(ClassificationJob).where(
                    ClassificationJob.created_at >= cutoff
                )
            )
            or 0
        )
        ai_queries = (
            await self.db.scalar(
                select(func.count()).select_from(LLMUsageLog).where(LLMUsageLog.created_at >= cutoff)
            )
            or 0
        )
        tokens_in = (
            await self.db.scalar(
                select(func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0)).where(
                    LLMUsageLog.created_at >= cutoff
                )
            )
            or 0
        )
        tokens_out = (
            await self.db.scalar(
                select(func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0)).where(
                    LLMUsageLog.created_at >= cutoff
                )
            )
            or 0
        )
        return {
            "total_users": total_users,
            "active_users": active_users,
            "documents": documents,
            "ai_queries": ai_queries,
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "total_tokens": int(tokens_in) + int(tokens_out),
        }

    async def login_activity(self, cutoff: datetime) -> list[dict]:
        rows = await self.db.execute(
            select(_day(AuditEvent.created_at).label("day"), func.count().label("n"))
            .where(AuditEvent.event_type == "login", AuditEvent.created_at >= cutoff)
            .group_by("day")
            .order_by("day")
        )
        return [{"date": r.day[:10], "logins": r.n} for r in rows]

    async def token_trend(self, cutoff: datetime) -> list[dict]:
        rows = await self.db.execute(
            select(
                _day(LLMUsageLog.created_at).label("day"),
                LLMUsageLog.module,
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("tokens"),
            )
            .where(LLMUsageLog.created_at >= cutoff)
            .group_by("day", LLMUsageLog.module)
            .order_by("day")
        )
        by_day: dict[str, dict] = {}
        for r in rows:
            date = r.day[:10]
            entry = by_day.setdefault(date, {"date": date, "M1": 0, "M2": 0, "M3": 0, "total": 0})
            if r.module in MODULES:
                entry[r.module] += int(r.tokens)
            entry["total"] += int(r.tokens)
        return list(by_day.values())

    async def feature_stats(self, cutoff: datetime) -> dict:
        usage_rows = await self.db.execute(
            select(
                _day(LLMUsageLog.created_at).label("day"),
                LLMUsageLog.module,
                func.count().label("n"),
            )
            .where(LLMUsageLog.created_at >= cutoff)
            .group_by("day", LLMUsageLog.module)
            .order_by("day")
        )
        modules: dict[str, list[dict]] = {m: [] for m in MODULES}
        for r in usage_rows:
            if r.module in modules:
                modules[r.module].append({"date": r.day[:10], "count": r.n})

        doc_rows = await self.db.execute(
            select(_day(ClassificationJob.created_at).label("day"), func.count().label("n"))
            .where(ClassificationJob.created_at >= cutoff)
            .group_by("day")
            .order_by("day")
        )
        documents = [{"date": r.day[:10], "count": r.n} for r in doc_rows]
        return {"modules": modules, "documents": documents}

    async def per_agent(self, cutoff: datetime) -> list[dict]:
        # Token spend grouped by classification agent (M1). Rows with no agent
        # (M2/M3) are excluded — this view is about agent-level attribution.
        rows = await self.db.execute(
            select(
                LLMUsageLog.agent_name,
                func.count().label("queries"),
                func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0).label("tokens_in"),
                func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0).label("tokens_out"),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("tokens"),
            )
            .where(LLMUsageLog.created_at >= cutoff, LLMUsageLog.agent_name.isnot(None))
            .group_by(LLMUsageLog.agent_name)
            .order_by(func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).desc())
        )
        return [
            {
                "agent_name": r.agent_name,
                "queries": r.queries,
                "tokens_in": int(r.tokens_in),
                "tokens_out": int(r.tokens_out),
                "tokens": int(r.tokens),
            }
            for r in rows
        ]

    async def per_vendor(self, cutoff: datetime) -> list[dict]:
        # Token spend grouped by vendor (M2 due diligence). Joins vendors so the
        # current legal name is shown; rows with no vendor (M1/M3) are excluded.
        rows = await self.db.execute(
            select(
                Vendor.legal_name,
                func.count().label("queries"),
                func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0).label("tokens_in"),
                func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0).label("tokens_out"),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("tokens"),
            )
            .join(Vendor, Vendor.id == LLMUsageLog.vendor_id)
            .where(LLMUsageLog.created_at >= cutoff, LLMUsageLog.vendor_id.isnot(None))
            .group_by(Vendor.legal_name)
            .order_by(func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).desc())
        )
        return [
            {
                "vendor_name": r.legal_name,
                "queries": r.queries,
                "tokens_in": int(r.tokens_in),
                "tokens_out": int(r.tokens_out),
                "tokens": int(r.tokens),
            }
            for r in rows
        ]

    async def per_user(self, cutoff: datetime) -> list[dict]:
        # Per-user AI usage (queries + tokens) within the window.
        usage_rows = await self.db.execute(
            select(
                LLMUsageLog.actor_id,
                func.count().label("queries"),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("tokens"),
            )
            .where(LLMUsageLog.created_at >= cutoff)
            .group_by(LLMUsageLog.actor_id)
        )
        usage_by_user = {r.actor_id: (r.queries, int(r.tokens)) for r in usage_rows}

        doc_rows = await self.db.execute(
            select(ClassificationJob.created_by, func.count().label("docs"))
            .where(ClassificationJob.created_at >= cutoff)
            .group_by(ClassificationJob.created_by)
        )
        docs_by_user = {r.created_by: r.docs for r in doc_rows}

        dd_rows = await self.db.execute(
            select(DDReport.created_by, func.count().label("docs"))
            .where(DDReport.created_at >= cutoff)
            .group_by(DDReport.created_by)
        )
        for r in dd_rows:
            docs_by_user[r.created_by] = docs_by_user.get(r.created_by, 0) + r.docs

        users = await self.db.execute(
            select(User).order_by(User.created_at)
        )
        result = []
        # Roles in one query to avoid N+1.
        role_rows = await self.db.execute(select(UserRole.user_id, UserRole.role))
        roles_by_user: dict = {}
        for uid, role in role_rows:
            roles_by_user.setdefault(uid, []).append(role)

        for u in users.scalars().all():
            queries, tokens = usage_by_user.get(u.id, (0, 0))
            result.append(
                {
                    "id": str(u.id),
                    "email": u.email,
                    "display_name": u.display_name,
                    "role": (roles_by_user.get(u.id) or ["—"])[0],
                    "documents": docs_by_user.get(u.id, 0),
                    "queries": queries,
                    "tokens": tokens,
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                }
            )
        return result
