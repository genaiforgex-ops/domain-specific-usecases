from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import ClassificationJob
from app.models.project import Project, RiskScore
from app.models.vendor import DDReport


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def operational_metrics(self) -> dict:
        m1_pending = await self.db.scalar(
            select(func.count()).select_from(ClassificationJob).where(
                ClassificationJob.status.in_(["pending", "processing", "ready"])
            )
        )
        m1_overrides = await self.db.scalar(
            select(func.count()).select_from(ClassificationJob).where(
                ClassificationJob.justification.isnot(None)
            )
        )
        m1_total = await self.db.scalar(select(func.count()).select_from(ClassificationJob))
        m2_pending = await self.db.scalar(
            select(func.count()).select_from(DDReport).where(DDReport.status != "signed_off")
        )
        m3_draft = await self.db.scalar(
            select(func.count()).select_from(RiskScore).where(RiskScore.status == "draft")
        )
        override_rate = (m1_overrides / m1_total * 100) if m1_total else 0
        return {
            "m1_queue_depth": m1_pending or 0,
            "m1_override_rate_pct": round(override_rate, 1),
            "m2_open_reports": m2_pending or 0,
            "m3_draft_scores": m3_draft or 0,
        }

    async def risk_trends(self) -> dict:
        result = await self.db.execute(
            select(
                Project.business_line,
                func.avg(RiskScore.final_inherent_score),
                func.avg(RiskScore.final_residual_score),
                func.count(RiskScore.id),
            )
            .join(RiskScore, RiskScore.project_id == Project.id)
            .group_by(Project.business_line)
        )
        rows = result.all()
        return {
            "by_business_line": [
                {
                    "business_line": r[0] or "Unassigned",
                    "avg_inherent": round(float(r[1] or 0), 2),
                    "avg_residual": round(float(r[2] or 0), 2),
                    "count": r[3],
                }
                for r in rows
            ]
        }
