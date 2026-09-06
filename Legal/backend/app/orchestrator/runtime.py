"""Request-scoped runtime context for agent tools.

ADK runs tools inside the async Runner (sync tools on a threadpool), detached
from the FastAPI request. Tools that need the DB or the acting user read them
from this contextvar, which the chat route sets for the duration of a turn.

Tools open their OWN short-lived ``SessionLocal`` rather than sharing the
request's session — a SQLAlchemy sync Session is not safe to share across the
threadpool threads ADK may use.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class RequestRuntime:
    user_id: int
    role: str
    mode: str = "review"
    # Mode tool gating: corpus tools stamp whether they ran / found hits so
    # Review can block open-web until corpora are empty.
    corpora_searched: bool = False
    corpora_had_hits: bool = False
    # Latency / freshness notes tools may append for the Thoughts panel.
    notes: list[str] = field(default_factory=list)


_current: contextvars.ContextVar[RequestRuntime | None] = contextvars.ContextVar(
    "orch_request_runtime", default=None
)


@contextmanager
def request_runtime(
    user_id: int, role: str, mode: str = "review"
) -> Iterator[RequestRuntime]:
    rt = RequestRuntime(user_id=user_id, role=role, mode=(mode or "review").lower())
    token = _current.set(rt)
    try:
        yield rt
    finally:
        _current.reset(token)


def current_runtime() -> RequestRuntime | None:
    return _current.get()


def mark_corpus_result(*, had_hits: bool) -> None:
    """Called by JFPSL / regulatory RAG tools after a search."""
    rt = _current.get()
    if rt is None:
        return
    rt.corpora_searched = True
    if had_hits:
        rt.corpora_had_hits = True


def web_allowed_for_mode() -> tuple[bool, str]:
    """Hard mode → tool rules for open web / fetch.

    Returns (allowed, denial_message_if_not).
    """
    rt = _current.get()
    if rt is None:
        return True, ""
    mode = rt.mode or "review"
    if mode == "draft":
        return (
            False,
            "Web search is blocked in DRAFT mode. Use the attached template / "
            "document or search_jfpsl_knowledge for JFPSL standard wording.",
        )
    if mode == "review":
        if not rt.corpora_searched:
            return (
                False,
                "In REVIEW mode, search attachments / search_jfpsl_knowledge / "
                "search_regulatory_knowledge first. Open web is only allowed when "
                "those corpora return nothing useful.",
            )
        if rt.corpora_had_hits:
            return (
                False,
                "In REVIEW mode, ground the answer in the retrieved corpus / "
                "attachments. Open web is blocked because corpus hits were found.",
            )
    return True, ""
