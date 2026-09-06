from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.contract import Contract


class ContractRevision(Base):
    """A prompt-based edit proposed against a contract (UC-01 document editor).

    Always a *proposal*: created with status="proposed", then either "applied"
    (its edited_text becomes the contract's text) or "discarded". Nothing is
    auto-finalized — the reviewer-control guardrail is enforced here.
    """

    __tablename__ = "contract_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    selection: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{description, original, revised}]
    changes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # [{kind, v1, v2}] — track-mode redline blocks for the frontend.
    diff_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contract: Mapped[Contract] = relationship()
