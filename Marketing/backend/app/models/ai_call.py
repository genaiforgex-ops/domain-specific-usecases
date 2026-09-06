"""AiCall model — one row per model/agent call, for full cost & latency tracing.

Every LLM / image-model call (brief extraction, copy generation, banner image)
writes a row here with its token usage and wall-clock latency. Cost is derived
from the tokens at write time (see app.services.pricing) and stored, so the
Admin dashboard reads real spend instead of an estimate.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiCall(Base):
    """One traced call to a model/agent."""

    __tablename__ = "ai_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 'brief_extract' | 'copy_generation' | 'banner_image'
    operation: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google")
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    # Attribution — both nullable (brief extraction runs before a brief exists).
    brief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    creative_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creatives.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_inr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok | error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
