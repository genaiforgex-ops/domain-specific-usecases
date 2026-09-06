from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    user_id: int | None
    role: str
    action_type: str
    module: str
    input_summary: str | None
    ai_output_summary: str | None
    confidence_score: float | None
    human_decision: str | None
    model_version: str | None
    ip_address: str | None
    session_id: str | None
    target_id: int | None
    extra: dict | None
    timestamp: datetime
