"""Request-scoped caching wrapper over ADK's DatabaseSessionService.

This is the short-term memory store: ADK persists each turn's events to the DB
(via ``postgresql+psycopg`` async engine), so a follow-up on the same
``session_id`` sees the full prior conversation. Long-term memory is the
optional event-compaction summarizer configured on the App.

The wrapper adds a per-request read cache (repeated ``get_session`` in one HTTP
request → 0 extra DB round-trips) using the stable public API only, so it stays
correct across ADK point releases. Writes go straight through
``super().append_event`` — durability is not deferred — and the cached Session
is the same object ADK mutates, so the cache never goes stale within a request.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import asynccontextmanager

from google.adk.events import Event
from google.adk.sessions import DatabaseSessionService, Session

logger = logging.getLogger("legalos.orchestrator")

_request_cache: contextvars.ContextVar[dict[str, Session] | None] = contextvars.ContextVar(
    "orch_session_cache", default=None
)


class CachingSessionService(DatabaseSessionService):
    @asynccontextmanager
    async def request_scope(self):
        """Enter a per-request session cache; discarded on exit."""
        token = _request_cache.set({})
        try:
            yield
        finally:
            _request_cache.reset(token)

    @staticmethod
    def _cache() -> dict[str, Session] | None:
        return _request_cache.get()

    async def create_session(self, *, app_name, user_id, state=None, session_id=None) -> Session:
        session = await super().create_session(
            app_name=app_name, user_id=user_id, state=state, session_id=session_id
        )
        cache = self._cache()
        if cache is not None:
            cache[session.id] = session
        return session

    async def get_session(self, *, app_name, user_id, session_id, config=None):
        cache = self._cache()
        if cache is not None and config is None and session_id in cache:
            logger.debug("[sessions] request-scope cache hit for %s", session_id)
            return cache[session_id]
        session = await super().get_session(
            app_name=app_name, user_id=user_id, session_id=session_id, config=config
        )
        if session is not None and cache is not None and config is None:
            cache[session_id] = session
        return session

    async def append_event(self, session: Session, event: Event) -> Event:
        result = await super().append_event(session, event)
        cache = self._cache()
        if cache is not None:
            cache[session.id] = session
        return result

    async def flush_and_cleanup(self, session_id: str) -> None:
        """No-op flush hook.

        Writes are already durable (append_event writes through). Kept so the
        pipeline can call it symmetrically with the finance-gpt blueprint, and
        so a batched-write optimization can be slotted in later without touching
        the pipeline.
        """
        return None

    async def warmup(self) -> None:
        """Touch the schema once at startup so the first request pays no
        table-introspection cost."""
        try:
            await self._prepare_tables()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[sessions] warmup skipped: %s", exc)
