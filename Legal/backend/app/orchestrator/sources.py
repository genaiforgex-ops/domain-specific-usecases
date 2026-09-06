"""Request-scoped sink for the sources a turn actually used.

Tools (web search, JFPSL RAG) run inside the ADK Runner — on a threadpool for
sync tools — detached from the FastAPI request. Like ``runtime.py``, they reach
back into the turn via a contextvar. The pipeline installs a fresh list at the
start of each turn; tools append the structured sources they returned; the
pipeline reads + dedupes them after the run to build the References list and to
persist them alongside the turn.

The contextvar holds a single shared list object, so appends from tool threads
(``list.append`` is atomic under the GIL) are visible to the pipeline that
installed it.
"""

from __future__ import annotations

import contextvars
import hashlib
from typing import Any

_sink: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "orch_sources_sink", default=None
)

_SNIPPET_CAP = 500
_CHUNK_TEXT_CAP = 4000


def start_collection() -> contextvars.Token:
    """Install a fresh sink for the current turn. Returns a reset token."""
    return _sink.set([])


def stop_collection(token: contextvars.Token) -> None:
    _sink.reset(token)


def record_sources(items: list[dict[str, Any]]) -> None:
    """Append the sources a tool relied on (no-op outside a turn)."""
    sink = _sink.get()
    if sink is None or not items:
        return
    sink.extend(items)


def collected_count() -> int:
    """Deduped source count so far — use to assign absolute citation indices."""
    return len(collected_sources())


def dedupe_key(item: dict[str, Any]) -> str:
    """The identity used to dedupe a source (and therefore to number its citation)."""
    return (item.get("chunk_id") or "").strip() or (
        (item.get("storage_key") or "").strip()
        or (item.get("url") or "").strip()
        or (item.get("title") or "").strip()
    )


def citation_numbers() -> dict[str, int]:
    """Map each collected source's dedupe key to its 1-based citation number.

    Tools must number their excerpts from this rather than counting their own
    results: two lanes searching the same regulator page produce the same source,
    dedupe collapses it, and any tool that assumed "my N results occupy the next N
    slots" then labels every later citation one slot too low — so ``[4]`` in the
    answer points at a different source than ``[4]`` in the References list.
    """
    return {
        key: i
        for i, item in enumerate(collected_sources(), start=1)
        if (key := dedupe_key(item))
    }


def make_chunk_id(prefix: str, *parts: str) -> str:
    """Stable chunk id: ``prefix:sha1[:12]`` over joined parts."""
    raw = "|".join((p or "").strip() for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def clip_snippet(text: str | None) -> str:
    return (text or "").strip()[:_SNIPPET_CAP]


def clip_chunk_text(text: str | None) -> str:
    return (text or "").strip()[:_CHUNK_TEXT_CAP]


def collected_sources() -> list[dict[str, Any]]:
    """Return the deduped sources gathered so far in this turn (order-stable).

    Dedupes by ``chunk_id`` when present so multiple excerpts from the same
    document remain separate citable entries. Falls back to doc-level keys for
    legacy tool payloads without ``chunk_id``.
    """
    sink = _sink.get()
    if not sink:
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in sink:
        chunk_id = (item.get("chunk_id") or "").strip()
        key = chunk_id or (
            (item.get("storage_key") or "").strip()
            or (item.get("url") or "").strip()
            or (item.get("title") or "").strip()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
