import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    business_line: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True)
    intake_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    risk_scores: Mapped[list["RiskScore"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    inherent_score: Mapped[float] = mapped_column(Float, nullable=False)
    residual_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_inherent_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_inherent_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_residual_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_version: Mapped[str] = mapped_column(String(32), default="v1")
    model_version: Mapped[str] = mapped_column(String(32), default="deterministic-v1")
    drivers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    override_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="risk_scores")
