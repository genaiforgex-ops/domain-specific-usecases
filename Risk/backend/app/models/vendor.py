import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(64), default="IN")
    cin: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    pan: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    gstin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    classification_jobs: Mapped[list["ClassificationJob"]] = relationship(back_populates="vendor")
    dd_reports: Mapped[list["DDReport"]] = relationship(back_populates="vendor")


class DDReport(Base):
    __tablename__ = "dd_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    red_flag_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weights_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outsourcing_checklist: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full rich due-diligence audit (BLANK_DATA-shaped: business identity,
    # security, reputation, legal, compliance, footprint, risk). Source of
    # truth that findings + red_flag_score are derived from.
    audit_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped["Vendor"] = relationship(back_populates="dd_reports")
    findings: Mapped[list["DDFinding"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class DDFinding(Base):
    __tablename__ = "dd_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dd_reports.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_tier: Mapped[str] = mapped_column(String(32), default="secondary")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    artifact_s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    dedupe_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    severity_weight: Mapped[float] = mapped_column(Float, default=1.0)
    disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped["DDReport"] = relationship(back_populates="findings")


class DDWeightConfig(Base):
    __tablename__ = "dd_weight_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    category_weights: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

