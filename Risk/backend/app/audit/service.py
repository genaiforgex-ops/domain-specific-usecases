import hashlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_id: uuid.UUID | None = None,
        payload: dict | None = None,
        before: dict | None = None,
        after: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            actor_id=actor_id,
            payload_json=payload,
            before_state=before,
            after_state=after,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def log_ai_call(
        self,
        module: str,
        entity_id: str,
        actor_id: uuid.UUID | None,
        model_version: str,
        prompt_hash: str,
        output: Any,
        kill_switch: bool,
    ) -> AuditEvent:
        return await self.log(
            event_type="ai.invocation",
            entity_type=module,
            entity_id=entity_id,
            actor_id=actor_id,
            payload={
                "model_version": model_version,
                "prompt_hash": prompt_hash,
                "output": output,
                "kill_switch_active": kill_switch,
            },
        )


def hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
