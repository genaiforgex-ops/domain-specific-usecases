"""Singletons for the orchestrator: session service, artifact service, runner.

Built lazily (first use / startup warmup) so importing the chat router never
fails the whole app if the model/session backend is momentarily unavailable.
The Runner is the ADK object that actually streams tokens; swapping the model
(via build_model / config) does not change any calling code.
"""

from __future__ import annotations

import logging

from google.adk.runners import Runner

from app.orchestrator import config as orch_config
from app.orchestrator.agent import build_app
from app.orchestrator.memory import CachingSessionService

logger = logging.getLogger("legalos.orchestrator")

_session_service: CachingSessionService | None = None
_runner: Runner | None = None


def get_session_service() -> CachingSessionService:
    global _session_service
    if _session_service is None:
        _session_service = CachingSessionService(db_url=orch_config.SESSION_DSN)
        logger.info("[orchestrator] session service initialized")
    return _session_service


def _build_artifact_service():
    if orch_config.ARTIFACT_BACKEND == "gcs" and orch_config.SESSION_BUCKET:
        from google.adk.artifacts import GcsArtifactService

        return GcsArtifactService(bucket_name=orch_config.SESSION_BUCKET)
    from google.adk.artifacts import InMemoryArtifactService

    return InMemoryArtifactService()


def get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = Runner(
            app=build_app(),
            session_service=get_session_service(),
            artifact_service=_build_artifact_service(),
        )
        logger.info("[orchestrator] runner initialized (app=%s)", orch_config.APP_NAME)
    return _runner


async def warmup() -> None:
    """Called from the FastAPI lifespan so the first request is fast."""
    get_runner()
    await get_session_service().warmup()
