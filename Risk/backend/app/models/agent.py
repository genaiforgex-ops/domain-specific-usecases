import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ClassificationAgent(Base):
    """A saved, named prompt configuration for the M1 classification use case.

    Each agent carries its own editable guidance for the RBI and SEBI calls plus
    the model/temperature to run them with. It only overrides the *guidance*
    block — the fixed grounding + JSON-output contract are always appended in the
    adapter, so a custom agent can never break the structured output the parser
    depends on. Deliberately a separate table from PromptTemplate: those rows are
    versioned/reseeded from code on startup and would clobber user-authored
    agents."""

    __tablename__ = "classification_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rbi_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sebi_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="gemini-2.5-flash")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Soft-archive rather than delete so past runs (which reference this id) keep
    # resolving a name; archived agents drop out of the pickable list.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClassificationAgentRun(Base):
    """One agent's result within a classification job — the unit the Review screen
    lays out side-by-side. A job with no selected agents produces zero of these
    (the built-in default run writes straight onto the job, unchanged)."""

    __tablename__ = "classification_agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classification_jobs.id"), nullable=False, index=True
    )
    # Nullable so a built-in default run can also be recorded as a row if ever
    # needed; a real agent run always sets it.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classification_agents.id"), nullable=True
    )
    # Snapshot of the agent's name so the comparison still reads correctly after
    # the agent is renamed or archived.
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    rbi_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rbi_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rbi_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sebi_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sebi_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sebi_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Exact prompts/model/temperature used, captured at run time for audit and
    # reproducibility even if the agent is later edited.
    agent_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["ClassificationJob"] = relationship("ClassificationJob", back_populates="agent_runs")
