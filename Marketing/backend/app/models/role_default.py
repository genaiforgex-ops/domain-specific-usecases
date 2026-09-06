"""RoleDefault — the single account new work auto-routes to, per role.

There is one row per assignable role (CW/ML/PL/DS). When a brief is submitted
it goes to the default Copywriter; at copy hand-off the three approver lanes and
the Designer are filled from their defaults. Only an Admin sets these; the person
a task lands on can still reassign it to a same-role peer afterwards.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RoleDefault(Base):
    __tablename__ = "role_defaults"

    role: Mapped[str] = mapped_column(String(8), primary_key=True)  # one of ROLES
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()  # noqa: F821
