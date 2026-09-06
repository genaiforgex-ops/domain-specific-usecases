import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.gemini_llm import (
    DEFAULT_GUIDANCE_RBI,
    DEFAULT_GUIDANCE_SEBI,
    GeminiLLMAdapter,
)
from app.audit.service import AuditService
from app.models.agent import ClassificationAgent

_LEARNINGS_HEADING = "REVIEWER LEARNINGS:"


def _append_learning(prompt: str, text: str) -> str:
    """Add `text` as a bullet under a single REVIEWER LEARNINGS section at the end
    of the prompt — creating the heading the first time, then accumulating bullets
    on later learnings so the section never duplicates."""
    prompt = prompt or ""
    bullet = f"- {text}"
    if _LEARNINGS_HEADING in prompt:
        return f"{prompt.rstrip()}\n{bullet}"
    return f"{prompt.rstrip()}\n\n{_LEARNINGS_HEADING}\n{bullet}"


class AgentService:
    """CRUD for M1 classification agents (user-authored prompt configurations)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def list_agents(self, active_only: bool = True) -> list[ClassificationAgent]:
        query = select(ClassificationAgent).order_by(ClassificationAgent.created_at.desc())
        if active_only:
            query = query.where(ClassificationAgent.is_active.is_(True))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_agent(self, agent_id: uuid.UUID) -> ClassificationAgent:
        result = await self.db.execute(
            select(ClassificationAgent).where(ClassificationAgent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise ValueError("Agent not found")
        return agent

    async def create_agent(self, data: dict, created_by: uuid.UUID | None) -> ClassificationAgent:
        agent = ClassificationAgent(**data, created_by=created_by)
        self.db.add(agent)
        await self.db.flush()
        await self.db.refresh(agent)
        await self.audit.log("m1.agent.created", "classification_agent", str(agent.id), actor_id=created_by, after=data)
        return agent

    async def update_agent(self, agent_id: uuid.UUID, data: dict) -> ClassificationAgent:
        agent = await self.get_agent(agent_id)
        # Only touch fields the caller actually sent (PATCH semantics).
        for field, value in data.items():
            setattr(agent, field, value)
        await self.db.flush()
        await self.db.refresh(agent)
        await self.audit.log("m1.agent.updated", "classification_agent", str(agent.id), after=data)
        return agent

    async def archive_agent(self, agent_id: uuid.UUID) -> ClassificationAgent:
        """Soft-delete: keep the row (past runs reference it) but drop it from the
        pickable list."""
        return await self.update_agent(agent_id, {"is_active": False})

    async def apply_learning(
        self,
        *,
        learning_info: str,
        source: str | None,
        mode: str,
        target_agent_id: uuid.UUID | None,
        base_agent_id: uuid.UUID | None,
        new_agent_name: str | None,
        actor_id: uuid.UUID | None,
    ) -> ClassificationAgent:
        """Fold a reviewer's override learning into an agent's prompt. `source`
        ("rbi"/"sebi") selects which of the agent's two prompts receives it — the
        other is left untouched.

        mode="existing": append to `target_agent_id` in place.
        mode="new": copy the prompt used for the overridden result (the
        `base_agent_id` agent, or the built-in defaults when null), append the
        learning to the `source` prompt, and save it as a new agent.
        """
        learning_info = (learning_info or "").strip()
        if not learning_info:
            raise ValueError("learning_info is required")
        reg = (source or "").lower()
        if reg not in ("rbi", "sebi"):
            raise ValueError("source must be 'rbi' or 'sebi' to target a prompt")
        field = "rbi_prompt" if reg == "rbi" else "sebi_prompt"

        if mode == "existing":
            if not target_agent_id:
                raise ValueError("target_agent_id is required for mode 'existing'")
            agent = await self.get_agent(target_agent_id)
            setattr(agent, field, _append_learning(getattr(agent, field), learning_info))
            await self.db.flush()
            await self.db.refresh(agent)
            await self.audit.log(
                "m1.agent.learning_added", "classification_agent", str(agent.id), actor_id=actor_id,
                payload={"regulator": reg, "learning": learning_info},
            )
            return agent

        if mode == "new":
            if not (new_agent_name or "").strip():
                raise ValueError("new_agent_name is required for mode 'new'")
            if base_agent_id is not None:
                base = await self.get_agent(base_agent_id)
                data = {
                    "rbi_prompt": base.rbi_prompt,
                    "sebi_prompt": base.sebi_prompt,
                    "model_version": base.model_version,
                    "temperature": base.temperature,
                }
            else:
                d = self.get_default_prompts()
                data = {
                    "rbi_prompt": d["rbi_prompt"],
                    "sebi_prompt": d["sebi_prompt"],
                    "model_version": d["model_version"],
                    "temperature": d["temperature"],
                }
            data[field] = _append_learning(data[field], learning_info)
            data["name"] = new_agent_name.strip()
            data["description"] = f"Created from an override learning ({reg.upper()})."
            return await self.create_agent(data, actor_id)

        raise ValueError("learning_mode must be 'existing' or 'new'")

    def get_default_prompts(self) -> dict:
        """The built-in guidance/model/temperature, so the editor can prefill a new
        agent with exactly today's behavior and let the user tweak from there."""
        return {
            "rbi_prompt": DEFAULT_GUIDANCE_RBI,
            "sebi_prompt": DEFAULT_GUIDANCE_SEBI,
            "model_version": GeminiLLMAdapter.model_version,
            "temperature": 0.0,
        }
