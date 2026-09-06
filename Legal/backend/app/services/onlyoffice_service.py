"""ONLYOFFICE Document Server integration — JWT config and callbacks."""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from jose import jwt

from app.config import settings

logger = logging.getLogger("legalos.onlyoffice")


def onlyoffice_enabled() -> bool:
    return bool(settings.onlyoffice_enabled and settings.onlyoffice_jwt_secret)


def document_key(version_id: int, sha256: str | None) -> str:
    """Stable key until file content changes (required by ONLYOFFICE)."""
    seed = f"v{version_id}:{sha256 or version_id}"
    return hashlib.sha256(seed.encode()).hexdigest()[:20]


def _file_extension(filename: str | None, mime_type: str | None) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    if mime_type and "pdf" in mime_type:
        return "pdf"
    if mime_type and ("word" in mime_type or "docx" in mime_type):
        return "docx"
    return "docx"


def is_office_editable(filename: str | None, mime_type: str | None) -> bool:
    ext = _file_extension(filename, mime_type)
    return ext in ("docx", "doc", "odt", "rtf")


def build_document_url(storage_key: str, user_id: int) -> str:
    from app.core.security import create_file_download_token

    base = settings.onlyoffice_document_base_url.rstrip("/")
    token = create_file_download_token(user_id, storage_key)
    return f"{base}/api/msa/files/{storage_key}?token={token}"


def build_editor_config(
    *,
    version_id: int,
    sha256: str | None,
    filename: str | None,
    mime_type: str | None,
    storage_key: str,
    user_id: int,
    user_name: str,
    tracker_id: int,
    parent_version_id: int,
    mode: str = "edit",
    can_edit: bool = True,
) -> dict[str, Any]:
    ext = _file_extension(filename, mime_type)
    userdata = json.dumps(
        {
            "tracker_id": tracker_id,
            "parent_version_id": parent_version_id,
            "user_id": user_id,
        }
    )
    editing = can_edit and mode == "edit"
    customization: dict[str, Any] = {
        # autosave flushes edits into the Document Server cache so the
        # command-service forcesave has changes to assemble (otherwise it
        # returns error 4 = "no changes"). It does NOT call our callback by
        # itself — only forcesave / final-save do.
        "autosave": True,
        "forcesave": False,
        "compactToolbar": False,
        "toolbarNoTabs": False,
        "reviewDisplay": "markup",
    }
    # When forcing is on, lock Track Changes ON so every human edit is recorded
    # as a native, author-attributed redline. When off, omit the key entirely so
    # the user keeps their own choice (passing False would lock tracking OFF).
    if settings.onlyoffice_force_track_changes:
        customization["review"] = {"trackChanges": True, "hoverMode": False}
    config: dict[str, Any] = {
        "document": {
            "fileType": ext,
            "key": document_key(version_id, sha256),
            "title": filename or f"document.{ext}",
            "url": build_document_url(storage_key, user_id),
            "permissions": {
                "edit": editing,
                "download": True,
                "print": True,
                "review": True,
                "comment": editing,
                "copy": True,
                "fillForms": editing,
                "modifyContentControl": editing,
                "modifyFilter": editing,
            },
        },
        "documentType": "word",
        "type": "desktop",
        "width": "100%",
        "height": "100%",
        "editorConfig": {
            "callbackUrl": f"{settings.onlyoffice_callback_base_url.rstrip('/')}/api/onlyoffice/callback",
            "mode": mode,
            "lang": "en",
            "user": {"id": str(user_id), "name": user_name or "Reviewer"},
            "customization": customization,
            "coEditing": {"mode": "strict", "change": False},
            "userdata": userdata,
        },
    }
    return config


def sign_config(config: dict[str, Any]) -> str:
    token = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_callback_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.onlyoffice_jwt_secret, algorithms=["HS256"])


def parse_callback_body(body: dict[str, Any]) -> dict[str, Any]:
    """ONLYOFFICE may wrap the callback payload in a signed token."""
    token = body.get("token")
    if token:
        return decode_callback_token(token)
    return body


def _command_base_url() -> str:
    base = settings.onlyoffice_command_base_url or settings.onlyoffice_public_url
    return base.rstrip("/")


def internal_document_url(url: str) -> str:
    """Rewrite an ONLYOFFICE callback download URL to a host the backend can reach.

    The Document Server builds cache URLs from its public address (e.g.
    http://localhost:8082), which is unreachable from inside the backend
    container. Point them at the internal command base (e.g. http://onlyoffice)
    while preserving the path and signed query string.
    """
    base = settings.onlyoffice_command_base_url
    if not base:
        return url
    base_parts = urlsplit(base)
    target = urlsplit(url)
    return urlunsplit(
        (
            base_parts.scheme or target.scheme,
            base_parts.netloc or target.netloc,
            target.path,
            target.query,
            target.fragment,
        )
    )


def _command_request_urls(document_key: str) -> list[str]:
    base = _command_base_url()
    shard = f"shardkey={document_key}"
    paths: list[str] = []
    if settings.onlyoffice_command_path.strip():
        paths.append(settings.onlyoffice_command_path.strip())
    paths.extend(["/command", "/coauthoring/CommandService.ashx"])

    urls: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = path if path.startswith("/") else f"/{path}"
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(f"{base}{normalized}?{shard}")
    return urls


def trigger_forcesave(document_key: str, userdata: str | None = None) -> int:
    """Ask ONLYOFFICE to save the open document. Returns the command error code (0 = ok).

    ``userdata`` is echoed back to our callback (forcesavetype 0 uses the command
    userdata, not the editor config one), so we pass tracker/version context here.
    """
    payload: dict[str, Any] = {"c": "forcesave", "key": document_key}
    if userdata is not None:
        payload["userdata"] = userdata
    if onlyoffice_enabled():
        token = jwt.encode(payload, settings.onlyoffice_jwt_secret, algorithm="HS256")
        body = {"token": token if isinstance(token, str) else token.decode("utf-8")}
    else:
        body = payload

    body_bytes = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    last_error: Exception | None = None

    for url in _command_request_urls(document_key):
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                raw = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.debug("ONLYOFFICE command endpoint not found: %s", url)
                last_error = exc
                continue
            logger.exception("ONLYOFFICE forcesave command failed: %s", exc)
            raise RuntimeError("ONLYOFFICE command service unreachable") from exc
        except urllib.error.URLError as exc:
            logger.exception("ONLYOFFICE forcesave command failed: %s", exc)
            raise RuntimeError("ONLYOFFICE command service unreachable") from exc

        if raw.get("token"):
            raw = decode_callback_token(raw["token"])
        return int(raw.get("error", -1))

    if last_error is not None:
        logger.exception("ONLYOFFICE forcesave command failed: no endpoint available")
        raise RuntimeError("ONLYOFFICE command service unreachable") from last_error
    raise RuntimeError("ONLYOFFICE command service unreachable")
