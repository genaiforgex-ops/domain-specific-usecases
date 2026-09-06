"""User model — authenticated accounts. Sign-in is by email + local password.
Each account is identified by a UUID. The ``role`` column is the account's
primary AMP role (CW/ML/PL/DS/AD)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import UUID, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# PL authors the brief; ML reviews/approves; CW writes copies; DS designs;
# ML approves design; PL final sign-off. AD is Admin with oversight.
ROLES = ("CW", "ML", "PL", "DS", "AD")


class User(Base):
    """An authenticated role account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    notifications_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
