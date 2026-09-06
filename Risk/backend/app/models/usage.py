import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMUsageLog(Base):
    """One row per AI model invocation, for usage/token accounting.

    Kept separate from audit_events (which is the immutable decision trail) so the
    Metrics panel can aggregate tokens cheaply without parsing JSONB payloads.
    Writes are best-effort — a failure here must never break the AI call itself.
    """

    __tablename__ = "llm_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    module: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    # Which classification agent drove the call (M1). "Default" for the built-in
    # run; null for non-agent modules (M2/M3). Enables per-agent token breakdowns.
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Which vendor the call was for (M2 due-diligence). Null for M1/M3. Enables
    # per-vendor token breakdowns; FK so the current vendor name is always used.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
