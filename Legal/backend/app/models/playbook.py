from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlaybookClause(Base):
    """A clause-type entry in the JFPSL contract playbook.

    AI uses these as the gold standard against which incoming contract clauses
    are compared (BRD UC-01 functional requirement #3).
    """

    __tablename__ = "playbook_clauses"

    id: Mapped[int] = mapped_column(primary_key=True)
    clause_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    contract_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MSA")
    standard_position: Mapped[str] = mapped_column(Text, nullable=False)
    risk_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    fallback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulatory_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    insert_anchor_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RegulatorySource(Base):
    """A single document in the JFPSL regulatory corpus, available for RAG-style
    keyword retrieval by the LegalResearch and LegalBot modules.
    """

    __tablename__ = "regulatory_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    regulator: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    reference: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    published_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeBaseEntry(Base):
    """LegalBot's source of truth — short FAQ-style entries with citations."""

    __tablename__ = "knowledge_base_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
