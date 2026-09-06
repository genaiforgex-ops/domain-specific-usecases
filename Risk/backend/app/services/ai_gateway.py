import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.factory import get_ai_adapter
from app.adapters.protocols import ClassificationResult
from app.audit.service import AuditService, hash_prompt
from app.core.config import get_settings
from app.models.config import ModuleAIConfig, PromptTemplate
from app.services.usage_service import record_llm_usage


class AIGateway:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)
        self.adapter = get_ai_adapter()

    async def _get_module_config(self, module: str) -> ModuleAIConfig | None:
        result = await self.db.execute(
            select(ModuleAIConfig).where(ModuleAIConfig.module == module)
        )
        return result.scalar_one_or_none()

    async def is_kill_switch_active(self, module: str) -> bool:
        config = await self._get_module_config(module)
        return config.kill_switch if config else False

    async def _get_active_prompt(self, module: str, name: str | None = None) -> PromptTemplate | None:
        query = select(PromptTemplate).where(
            PromptTemplate.module == module, PromptTemplate.is_active.is_(True)
        )
        if name is not None:
            query = query.where(PromptTemplate.name == name)
        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def classify(
        self,
        text: str,
        clauses: list[dict],
        module: str = "M1",
        regulator: str = "RBI",
        entity_id: str | None = None,
        actor_id: uuid.UUID | None = None,
        system_prompt: str | None = None,
        model_version: str | None = None,
        temperature: float | None = None,
        agent_name: str | None = None,
    ) -> ClassificationResult | None:
        kill_switch = await self.is_kill_switch_active(module)
        if kill_switch:
            await self.audit.log_ai_call(
                module=module,
                entity_id=entity_id or "unknown",
                actor_id=actor_id,
                model_version="disabled",
                prompt_hash="",
                output=None,
                kill_switch=True,
            )
            return None

        # Prompts are stored per regulator (e.g. "M1_RBI", "M1_SEBI") so each
        # call picks up the guidance for the regulator it's actually classifying
        # under. When no DB row exists the adapter falls back to its in-code
        # default — prompt_text stays None so the audit log records that the
        # code default (not a DB-versioned prompt) drove this call.
        if system_prompt is not None:
            # A classification agent supplied its own guidance for this call — it
            # wins over both the DB template and the in-code default.
            prompt_text = system_prompt
        elif get_settings().m1_use_code_prompt:
            # Local-dev override: skip the DB row entirely so prompt_text stays
            # None and the adapter uses its in-code DEFAULT_GUIDANCE_* text.
            prompt_text = None
        else:
            prompt = await self._get_active_prompt(module, name=f"{module}_{regulator.upper()}")
            prompt_text = prompt.template_text if prompt else None
        start = time.monotonic()
        result = await self.adapter.classify(
            text,
            clauses,
            module,
            regulator=regulator,
            system_prompt=prompt_text,
            model_version=model_version,
            temperature=temperature,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        await self.audit.log_ai_call(
            module=module,
            entity_id=entity_id or "unknown",
            actor_id=actor_id,
            model_version=result.model_version,
            prompt_hash=hash_prompt(prompt_text or f"code-default:{module}_{regulator.upper()}"),
            output={
                "label": result.label,
                "confidence": result.confidence,
                "clause_ids": result.clause_ids,
                "reasoning": result.reasoning,
                "latency_ms": latency_ms,
            },
            kill_switch=False,
        )
        await record_llm_usage(
            self.db,
            actor_id=actor_id,
            module=module,
            operation="classify",
            agent_name=agent_name,
            model_version=result.model_version,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_ms=latency_ms,
        )
        return result
