"""ApprovalOtp — server-side state for one issued email-approval code.

The signed token an approver carries is self-contained, but a guess limit cannot
be: a counter kept inside the token is defeated by simply replaying the first
token, whose count is zero and whose signature stays valid until it expires. So
each issued code gets a row here, keyed by the token's `jti`, and the attempt
count and single-use flag live on that row — replaying any copy of the token
lands on the same row and the same exhausted budget.

Rows are disposable: once expired they carry no meaning and can be pruned.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApprovalOtp(Base):
    __tablename__ = "approval_otps"

    # The token's `jti` claim — the join between a signed token and this row.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Wrong guesses so far. Once this hits the cap the code is dead and the
    # approver has to request a fresh one from their email.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Set the moment a code is accepted, so a correct code can't be used twice.
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
