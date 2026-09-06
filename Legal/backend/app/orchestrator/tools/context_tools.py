"""Agent-initiated context retrieval tools.

The pipeline injects explicitly attached/`@`-mentioned context up front, but an
agent may also decide mid-conversation that it needs a specific MSA document or
email thread. These tools give it that access, scoped to the acting user via the
request runtime. Each opens its own short-lived DB session (safe on the ADK tool
threadpool) and enforces the same access checks as the REST layer.
"""

from __future__ import annotations

import logging

from google.adk.tools import FunctionTool

from app.database import SessionLocal
from app.models.user import User
from app.orchestrator.context import _msa_version_text
from app.orchestrator.runtime import current_runtime
from app.services.gmail_service import get_gmail_service
from app.services.msa_access import ACCESS_VIEW, load_tracker_with_access

logger = logging.getLogger("legalos.orchestrator")

_NO_ACCESS = "That document is not available to you, or could not be found."


def get_msa_document(tracker_id: int, version_id: int | None = None) -> str:
    """Fetch the text of an MSA/NDA document by tracker id (latest version if
    ``version_id`` is omitted). Returns the document text or an access notice."""
    rt = current_runtime()
    if rt is None:
        return _NO_ACCESS
    db = SessionLocal()
    try:
        user = db.get(User, rt.user_id)
        if user is None:
            return _NO_ACCESS
        load_tracker_with_access(tracker_id, user, db, min_level=ACCESS_VIEW)
        text = _msa_version_text(db, tracker_id, version_id)
        return text or _NO_ACCESS
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_msa_document failed: %s", exc)
        return _NO_ACCESS
    finally:
        db.close()


def get_gmail_thread(thread_id: str) -> str:
    """Fetch an email thread as plain text by its Gmail thread id."""
    rt = current_runtime()
    if rt is None:
        return _NO_ACCESS
    db = SessionLocal()
    try:
        user = db.get(User, rt.user_id)
        if user is None:
            return _NO_ACCESS
        return get_gmail_service().thread_as_text(db, user, thread_id) or _NO_ACCESS
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_gmail_thread failed: %s", exc)
        return _NO_ACCESS
    finally:
        db.close()


get_msa_document_tool = FunctionTool(get_msa_document)
get_gmail_thread_tool = FunctionTool(get_gmail_thread)
