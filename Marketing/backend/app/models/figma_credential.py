"""FigmaCredential — a user's own Figma OAuth token.

Figma auth is per-user: each Designer connects their own Figma account through the
in-app OAuth flow, and the resulting dynamic-client registration + token set land
here (one row per user). The export path loads the acting user's row, so no two
users ever share a Figma connection.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FigmaCredential(Base):
    __tablename__ = "figma_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # The OAuth dynamic-client registration (client_id / client_secret) and the
    # token set (access + refresh). Kept as JSON so the dict stays a drop-in for
    # the shape the mcp_client already works with.
    client_info: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tokens: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # The connected Figma account's handle/email, for display (best-effort).
    figma_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()  # noqa: F821
