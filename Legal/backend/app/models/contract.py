from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contract(Base):
    """UC-01 Contract Review: a contract uploaded for AI review."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(64), nullable=False, default="MSA")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_guidelines: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_suggestions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    change_history: Mapped[list | None] = mapped_column(JSON, nullable=True)

    clauses: Mapped[list["ContractClause"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan", order_by="ContractClause.order_index"
    )


class ContractClause(Base):
    __tablename__ = "contract_clauses"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(256), nullable=True)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_flag: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewer_edit: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    references: Mapped[list | None] = mapped_column(JSON, nullable=True)

    contract: Mapped[Contract] = relationship(back_populates="clauses")
