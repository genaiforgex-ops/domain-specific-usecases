"""SSE event framing helpers.

Token stream (`partial:true`) → final (`partial:false`) → optional headline →
`thinking` status events → structured `thought` steps → `event: error` on failure.
All payloads are single `data:` JSON lines terminated by a blank line.
"""

from __future__ import annotations

import json
from typing import Any


def _data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def thinking(text: str) -> str:
    """UX status line, emitted before tool calls / agent transfers."""
    return _data({"type": "thinking", "text": text})


def thought(
    *,
    thought_id: str,
    kind: str,
    title: str = "Thinking",
    detail: str | None = None,
    items: list[dict[str, Any]] | None = None,
) -> str:
    """Structured reasoning / tool-trace step for the Thoughts panel."""
    payload: dict[str, Any] = {
        "type": "thought",
        "id": thought_id,
        "kind": kind,
        "title": title,
    }
    if detail:
        payload["detail"] = detail
    if items:
        payload["items"] = items
    return _data(payload)


def partial(chunk: str, session_id: str) -> str:
    """A streamed token chunk (response still in progress)."""
    return _data({"text": chunk, "partial": True, "session_id": session_id})


def final(
    text: str,
    session_id: str,
    headline: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    turn_id: int | None = None,
    thoughts: list[dict[str, Any]] | None = None,
) -> str:
    """The terminal message for a turn. Always emitted exactly once."""
    payload: dict[str, Any] = {"text": text, "partial": False, "session_id": session_id}
    if headline:
        payload["headline"] = headline
    if sources:
        payload["sources"] = sources
    if turn_id is not None:
        payload["turn_id"] = turn_id
    if thoughts:
        payload["thoughts"] = thoughts
    return _data(payload)


def headline(text: str, session_id: str) -> str:
    return _data({"headline": text, "session_id": session_id})


def safety_block(message: str, session_id: str) -> str:
    """Terminal event when input armor blocks the request."""
    return _data(
        {"text": message, "partial": False, "session_id": session_id, "blocked": True}
    )


def error(message: str) -> str:
    """Named error event per the SSE spec."""
    return f"event: error\ndata: {json.dumps({'error': message})}\n\n"
