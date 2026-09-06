import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.models.control import Control, ControlTest
from app.models.project import Project, RiskScore
from app.models.scoring import ScoringConfig
from app.services.ai_gateway import AIGateway

FACTOR_KEYS = [
    "customer_impact",
    "data_sensitivity",
    "transaction_volume",
    "vendor_dependency",
    "regulatory_exposure",
    "technology_complexity",
]

OUTCOME_MULTIPLIER = {"pass": 0.0, "partial": 0.5, "fail": 1.0}

SCALE_BANDS = [
    (5, "Low"),
    (12, "Medium"),
    (20, "High"),
    (25, "Critical"),
]


class ScoringService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)
        self.ai = AIGateway(db)

    async def get_active_config(self) -> ScoringConfig:
        result = await self.db.execute(
            select(ScoringConfig).where(ScoringConfig.is_active.is_(True)).limit(1)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise ValueError("No active scoring config")
        return config

    def _compute_inherent(self, intake: dict, weights: dict) -> tuple[float, list[dict]]:
        drivers = []
        total = 0.0
        for key in FACTOR_KEYS:
            raw = intake.get(key, 1)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 1.0
            value = max(1.0, min(5.0, value))
            w = weights.get(key, 1.0)
            contribution = value * w
            total += contribution
            drivers.append({"factor": key, "value": value, "weight": w, "contribution": round(contribution, 2)})
        drivers.sort(key=lambda d: d["contribution"], reverse=True)
        inherent = min(25.0, round(total, 2))
        return inherent, drivers[:5]

    def _band(self, score: float) -> str:
        for threshold, label in SCALE_BANDS:
            if score <= threshold:
                return label
        return "Critical"

    async def _control_penalty(self, project_id: uuid.UUID) -> float:
        result = await self.db.execute(
            select(ControlTest).where(ControlTest.project_id == project_id)
        )
        tests = result.scalars().all()
        if not tests:
            return 0.0
        penalty = 0.0
        for t in tests:
            penalty += OUTCOME_MULTIPLIER.get(t.outcome, 0.5) * 2.0
        return min(15.0, penalty)

    async def compute_score(
        self, project_id: uuid.UUID, actor_id: uuid.UUID | None, persist: bool = True
    ) -> RiskScore:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one()
        config = await self.get_active_config()
        weights = json.loads(config.factor_weights)

        inherent, drivers = self._compute_inherent(project.intake_data, weights)
        penalty = await self._control_penalty(project_id)
        residual = max(1.0, round(inherent - penalty, 2))

        score = RiskScore(
            project_id=project_id,
            inherent_score=inherent,
            residual_score=residual,
            ai_inherent_score=inherent,
            final_inherent_score=inherent,
            final_residual_score=residual,
            scale_version=config.version,
            drivers={
                "top_factors": drivers,
                "inherent_band": self._band(inherent),
                "residual_band": self._band(residual),
                "control_penalty": penalty,
            },
            status="draft",
        )
        if persist:
            self.db.add(score)
            await self.db.flush()
            await self.audit.log(
                "score.computed",
                "risk_score",
                str(score.id),
                actor_id=actor_id,
                after={"inherent": inherent, "residual": residual},
            )
        return score

    async def what_if(
        self, project_id: uuid.UUID, control_outcomes: dict[str, str]
    ) -> dict:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one()
        config = await self.get_active_config()
        weights = json.loads(config.factor_weights)
        inherent, drivers = self._compute_inherent(project.intake_data, weights)
        penalty = sum(OUTCOME_MULTIPLIER.get(o, 0.5) * 2.0 for o in control_outcomes.values())
        penalty = min(15.0, penalty)
        residual = max(1.0, round(inherent - penalty, 2))
        return {
            "inherent_score": inherent,
            "residual_score": residual,
            "drivers": drivers,
            "control_penalty": penalty,
        }

    async def override_score(
        self,
        score_id: uuid.UUID,
        inherent: float,
        residual: float,
        justification: str,
        user_id: uuid.UUID,
    ) -> RiskScore:
        if len(justification.strip()) < 20:
            raise ValueError("Justification must be at least 20 characters")
        result = await self.db.execute(select(RiskScore).where(RiskScore.id == score_id))
        score = result.scalar_one()
        before = {
            "final_inherent": score.final_inherent_score,
            "final_residual": score.final_residual_score,
        }
        score.final_inherent_score = inherent
        score.final_residual_score = residual
        score.override_justification = justification
        score.overridden_by = user_id
        score.status = "confirmed"
        await self.audit.log(
            "score.override",
            "risk_score",
            str(score.id),
            actor_id=user_id,
            before=before,
            after={"inherent": inherent, "residual": residual},
        )
        await self.db.flush()
        return score

    async def recompute_on_control_failure(self, project_id: uuid.UUID) -> RiskScore | None:
        result = await self.db.execute(
            select(ControlTest)
            .where(ControlTest.project_id == project_id, ControlTest.outcome == "fail")
            .limit(1)
        )
        if not result.scalar_one_or_none():
            return None
        return await self.compute_score(project_id, None, persist=True)
