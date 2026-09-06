from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClauseBankEntry(Base):
    """Versioned, insert-ready clause text linked to playbook positions."""

    __tablename__ = "clause_bank_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    playbook_clause_id: Mapped[int | None] = mapped_column(
        ForeignKey("playbook_clauses.id", ondelete="SET NULL"),
        nullable=True,
    )
    contract_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    clause_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="preferred")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    regulatory_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
