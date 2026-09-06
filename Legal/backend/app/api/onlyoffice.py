"""ONLYOFFICE Document Server callback handler."""

from __future__ import annotations

import json
import logging
import urllib.request

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.msa import MSATracker
from app.models.msa_version import MSADocumentVersion
from app.models.user import User
from app.services.audit_service import write_audit
from app.services.document_parser import parse_document
from app.services.document_storage import get_document_storage
from app.services.msa_version_service import create_version
from app.services.onlyoffice_service import (
    internal_document_url,
    onlyoffice_enabled,
    parse_callback_body,
)

logger = logging.getLogger("legalos.onlyoffice")

router = APIRouter(prefix="/api/onlyoffice", tags=["onlyoffice"])


@router.post("/callback")
async def onlyoffice_callback(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receive save notifications from ONLYOFFICE Document Server."""
    if not onlyoffice_enabled():
        return {"error": 0}

    raw = await request.json()
    try:
        body = parse_callback_body(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ONLYOFFICE callback JWT decode failed: %s", exc)
        return {"error": 1}

    status = body.get("status")
    # 2 = ready to save; 6 = forcesave while editing
    if status not in (2, 6):
        return {"error": 0}

    download_url = body.get("url")
    if not download_url:
        logger.warning("ONLYOFFICE callback missing download url")
        return {"error": 1}

    userdata_raw = body.get("userdata") or ""
    try:
        userdata = json.loads(userdata_raw) if userdata_raw else {}
    except json.JSONDecodeError:
        userdata = {}

    tracker_id = userdata.get("tracker_id")
    parent_version_id = userdata.get("parent_version_id")
    user_id = userdata.get("user_id")
    if not tracker_id or not parent_version_id:
        logger.warning("ONLYOFFICE callback missing userdata: %s", userdata)
        return {"error": 1}

    tracker = db.get(MSATracker, tracker_id)
    parent = db.get(MSADocumentVersion, parent_version_id)
    user = db.get(User, user_id) if user_id else None
    if tracker is None or parent is None or parent.tracker_id != tracker_id:
        logger.warning("ONLYOFFICE callback unknown tracker/version")
        return {"error": 1}

    fetch_url = internal_document_url(download_url)
    try:
        with urllib.request.urlopen(fetch_url, timeout=120) as resp:  # noqa: S310
            file_bytes = resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("ONLYOFFICE download failed (%s): %s", fetch_url, exc)
        return {"error": 1}

    filename = parent.filename or f"{tracker.vendor_name}_edited.docx"
    mime_type = parent.mime_type or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        extracted = parse_document(file_bytes, filename, mime_type)
    except Exception:  # noqa: BLE001
        extracted = parent.extracted_text

    storage_key, sha = get_document_storage().upload(file_bytes, filename, mime_type)
    create_version(
        db,
        tracker,
        source="legal_redline",
        extracted_text=extracted,
        user=user,
        filename=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        sha256=sha,
        parent_version_id=parent.id,
        run_compare=True,
        ip_address=None,
        session_id=None,
    )
    if tracker.status != "executed":
        tracker.status = "redlined"

    if user:
        write_audit(
            db,
            user=user,
            action_type="msa_onlyoffice_saved",
            module="msa_automation",
            input_summary=f"tracker={tracker_id} parent_v={parent.version_number}",
            human_decision="applied",
            target_id=tracker.id,
        )
    db.commit()
    return {"error": 0}
