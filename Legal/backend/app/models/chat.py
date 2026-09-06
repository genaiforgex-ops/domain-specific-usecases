"""Chatbot persistence models.

`ChatSession` is the app-owned sidebar record (title, ownership, activity). The
ADK `DatabaseSessionService` owns the conversation events in its own tables; we
keep only this lightweight index plus per-turn metrics.

`ChatTurn` is the durable per-turn log (the blueprint's `llm_turn_metrics`):
one row per user→assistant exchange, used for history replay, the sidebar
preview, token/latency accounting, and later personalization.
"""

from datetime import datetime

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    # Matches the ADK session id (string), so the two stores line up.
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New Chat Session")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatShare(Base):
    """A chat session shared (read-only) with another LegalOS user."""

    __tablename__ = "chat_shares"
    __table_args__ = (
        UniqueConstraint("session_id", "shared_with_user_id", name="uq_chat_share_session_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    shared_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    shared_with_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatTurn(Base):
    __tablename__ = "llm_turn_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    bot_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Structured references the assistant actually used this turn (web / template).
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # Structured Thoughts panel steps for this turn (plan / search / links / docs).
    thoughts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # Composer mode for this turn (review / research / draft).
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # User rating of the answer: 1 = helpful, -1 = not helpful, NULL = none.
    feedback: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Optional free-text detail the user submitted alongside the rating.
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatAttachment(Base):
    """Durable chat upload — parsed text keyed by attachment_id."""

    __tablename__ = "chat_attachments"

    attachment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
