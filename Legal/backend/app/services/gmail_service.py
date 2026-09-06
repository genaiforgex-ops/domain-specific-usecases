"""Gmail OAuth, read APIs, and message polling for LegalOS modules."""

from __future__ import annotations

import base64
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.gmail_credential import GmailCredential
from app.models.user import User
from app.services.document_parser import parse_document

logger = logging.getLogger(__name__)

# Google OAuth scopes required by LegalOS (feature → scope).
#
# Gmail (live today — Task Manager poll, MSA vendor threads, AI drafts, send):
#   gmail.readonly  — read full messages, threads, attachments, labels
#   gmail.send      — /messages/send (MSA send + draft send)
#   gmail.modify    — message/label updates beyond send (covers read+send too)
#   gmail.metadata  — header/label listing without body (lighter reads)
#
# Drive / Docs / Sheets (connectors + native file access; Drive alone only
# lists/reads blobs — Docs/Sheets APIs needed for native documents):
#   drive.file      — files the user opens/creates with LegalOS
#   documents       — Google Docs API
#   spreadsheets    — Google Sheets API
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.metadata",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
]
GMAIL_SCOPES = GOOGLE_OAUTH_SCOPES  # alias used by authorization_url

_MAX_PROCESSED_IDS = 2000
_HTTP_RETRIES = 3
_HTTP_RETRY_DELAY_SEC = 1.5


def _urlopen_with_retry(req: urllib.request.Request, *, timeout: float) -> Any:
    """Open URL with short retries for transient Docker/DNS failures."""
    last_exc: Exception | None = None
    for attempt in range(1, _HTTP_RETRIES + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, socket.gaierror, OSError) as exc:
            last_exc = exc
            # Do not retry permanent HTTP errors (4xx/5xx) — only transport/DNS.
            if isinstance(exc, urllib.error.HTTPError):
                raise
            if attempt >= _HTTP_RETRIES:
                break
            logger.warning(
                "Gmail HTTP transient failure (attempt %d/%d): %s",
                attempt,
                _HTTP_RETRIES,
                exc,
            )
            time.sleep(_HTTP_RETRY_DELAY_SEC * attempt)
    assert last_exc is not None
    raise last_exc


def _label_query_part(label: str) -> str:
    """Gmail search label clause — quote names with spaces or slashes."""
    label = label.strip()
    if not label:
        return ""
    if any(c in label for c in (' ', "/", "-", "&", "(")):
        return f'label:"{label}"'
    return f"label:{label}"


@dataclass
class ParsedEmail:
    message_id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    body: str
    snippet: str
    date: str | None
    sender_name: str
    sender_email: str


def _parse_from_header(from_addr: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*<([^>]+)>$", from_addr.strip())
    if match:
        return match.group(1).strip().strip('"'), match.group(2).strip()
    if "@" in from_addr:
        return from_addr.strip(), from_addr.strip()
    return from_addr.strip(), ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", errors="replace")
    if mime == "text/html" and payload.get("body", {}).get("data"):
        raw = base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", errors="replace")
        return _strip_html(raw)
    plain = ""
    html = ""
    for part in payload.get("parts", []):
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            text = _extract_body(part)
            if text:
                plain = text
        elif part_mime == "text/html" and not plain:
            text = _extract_body(part)
            if text:
                html = text
        else:
            nested = _extract_body(part)
            if nested and not plain:
                plain = nested
    return plain or html


def _headers_map(msg: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def parse_gmail_message(msg: dict) -> ParsedEmail:
    headers = _headers_map(msg)
    from_addr = headers.get("from", "")
    sender_name, sender_email = _parse_from_header(from_addr)
    return ParsedEmail(
        message_id=msg["id"],
        thread_id=msg.get("threadId", ""),
        subject=headers.get("subject", "(no subject)"),
        from_addr=from_addr,
        to_addr=headers.get("to", ""),
        body=_extract_body(msg.get("payload", {})),
        snippet=msg.get("snippet", ""),
        date=headers.get("date"),
        sender_name=sender_name,
        sender_email=sender_email,
    )


class GmailService:
    def __init__(self) -> None:
        self.client_id = settings.gmail_client_id
        self.client_secret = settings.gmail_client_secret
        self.redirect_uri = settings.gmail_redirect_uri

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_OAUTH_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    def exchange_code(self, code: str) -> dict:
        data = urllib.parse.urlencode(
            {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        with _urlopen_with_retry(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def fetch_connected_email(self, access_token: str) -> str:
        """Return the Gmail address for the authorized account."""
        profile = self._api(access_token, "/profile")
        return profile.get("emailAddress", "")

    def _get_credential(self, db: Session, user: User) -> GmailCredential:
        cred = db.execute(
            select(GmailCredential).where(GmailCredential.user_id == user.id)
        ).scalar_one_or_none()
        if cred is None:
            raise RuntimeError("Gmail not connected for this user")
        return cred

    def _refresh_if_needed(self, db: Session, cred: GmailCredential) -> str:
        if cred.token_expiry and cred.token_expiry > datetime.now(timezone.utc) + timedelta(minutes=2):
            return cred.access_token
        if not cred.refresh_token:
            return cred.access_token
        data = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": cred.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        with _urlopen_with_retry(req, timeout=30) as resp:
            tok = json.loads(resp.read().decode())
        cred.access_token = tok["access_token"]
        if "expires_in" in tok:
            cred.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tok["expires_in"]))
        db.commit()
        return cred.access_token

    def _access_token(self, db: Session, user: User) -> str:
        cred = self._get_credential(db, user)
        return self._refresh_if_needed(db, cred)

    def _api(self, access_token: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
        url = f"https://gmail.googleapis.com/gmail/v1/users/me{path}"
        headers = {"Authorization": f"Bearer {access_token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with _urlopen_with_retry(req, timeout=60) as resp:
            return json.loads(resp.read().decode())

    def save_credentials(self, db: Session, user: User, token_response: dict, email: str) -> GmailCredential:
        expiry = None
        if "expires_in" in token_response:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=int(token_response["expires_in"]))
        existing = db.execute(
            select(GmailCredential).where(GmailCredential.user_id == user.id)
        ).scalar_one_or_none()
        if existing:
            existing.access_token = token_response["access_token"]
            existing.refresh_token = token_response.get("refresh_token") or existing.refresh_token
            existing.token_expiry = expiry
            existing.email = email
            db.commit()
            db.refresh(existing)
            return existing
        cred = GmailCredential(
            user_id=user.id,
            email=email,
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            token_expiry=expiry,
        )
        db.add(cred)
        db.commit()
        db.refresh(cred)
        return cred

    def list_labels(self, db: Session, user: User) -> list[dict]:
        token = self._access_token(db, user)
        data = self._api(token, "/labels")
        return data.get("labels", [])

    def list_messages(
        self,
        db: Session,
        user: User,
        *,
        query: str = "",
        max_results: int = 20,
        page_token: str | None = None,
    ) -> tuple[list[dict], str | None]:
        token = self._access_token(db, user)
        path = f"/messages?maxResults={max_results}"
        if query:
            path += f"&q={urllib.parse.quote(query)}"
        if page_token:
            path += f"&pageToken={urllib.parse.quote(page_token)}"
        listing = self._api(token, path)
        summaries: list[dict] = []
        for mid in listing.get("messages", []):
            msg = self._api(
                token,
                f"/messages/{mid['id']}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=To&metadataHeaders=Date",
            )
            parsed = parse_gmail_message(msg)
            summaries.append(
                {
                    "id": parsed.message_id,
                    "thread_id": parsed.thread_id,
                    "subject": parsed.subject,
                    "from_addr": parsed.from_addr,
                    "to_addr": parsed.to_addr,
                    "snippet": parsed.snippet,
                    "date": parsed.date,
                }
            )
        return summaries, listing.get("nextPageToken")

    def fetch_messages_for_query(
        self,
        db: Session,
        user: User,
        query: str,
        *,
        max_total: int = 100,
        processed_ids: set[str] | None = None,
        exclude_processed: bool = True,
    ) -> list[ParsedEmail]:
        """Paginate Gmail query and return full parsed messages."""
        if not settings.gmail_enabled or not self.is_configured():
            return []
        cred = db.execute(
            select(GmailCredential).where(GmailCredential.user_id == user.id)
        ).scalar_one_or_none()
        if cred is None:
            return []
        token = self._refresh_if_needed(db, cred)
        seen = processed_ids or set()
        parsed: list[ParsedEmail] = []
        page_token: str | None = None
        while len(parsed) < max_total:
            batch_size = min(50, max_total - len(parsed))
            path = f"/messages?maxResults={batch_size}&q={urllib.parse.quote(query)}"
            if page_token:
                path += f"&pageToken={urllib.parse.quote(page_token)}"
            listing = self._api(token, path)
            messages = listing.get("messages", [])
            if not messages:
                break
            for mid in messages:
                if exclude_processed and mid["id"] in seen:
                    continue
                msg = self._api(token, f"/messages/{mid['id']}?format=full")
                parsed.append(parse_gmail_message(msg))
                if len(parsed) >= max_total:
                    break
            page_token = listing.get("nextPageToken")
            if not page_token:
                break
        return parsed

    def poll_recent_messages(
        self,
        db: Session,
        user: User,
        *,
        newer_than_days: int = 7,
        max_results: int = 100,
        processed_ids: set[str] | None = None,
        exclude_processed: bool = False,
    ) -> list[ParsedEmail]:
        """All mail in the lookback window — matches mailbox with no label filter."""
        q = f"newer_than:{newer_than_days}d"
        return self.fetch_messages_for_query(
            db,
            user,
            q,
            max_total=max_results,
            processed_ids=processed_ids,
            exclude_processed=exclude_processed,
        )

    def search_messages(
        self,
        db: Session,
        user: User,
        *,
        subject: str | None = None,
        from_addr: str | None = None,
        label: str | None = None,
        newer_than_days: int | None = None,
        q: str | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        parts: list[str] = []
        if q:
            parts.append(q)
        if subject:
            parts.append(f'subject:"{subject}"')
        if from_addr:
            parts.append(f"from:{from_addr}")
        if label:
            parts.append(_label_query_part(label))
        if newer_than_days is not None:
            parts.append(f"newer_than:{newer_than_days}d")
        query = " ".join(parts)
        rows, _ = self.list_messages(db, user, query=query, max_results=max_results)
        return rows

    def get_message(self, db: Session, user: User, message_id: str) -> ParsedEmail:
        token = self._access_token(db, user)
        msg = self._api(token, f"/messages/{message_id}?format=full")
        return parse_gmail_message(msg)

    def get_thread(self, db: Session, user: User, thread_id: str) -> list[ParsedEmail]:
        token = self._access_token(db, user)
        data = self._api(token, f"/threads/{thread_id}?format=full")
        return [parse_gmail_message(m) for m in data.get("messages", [])]

    def thread_context_for_ai(
        self,
        messages: list[ParsedEmail],
        reply_to_message_id: str,
    ) -> dict:
        """Build structured context for AI — summary of prior mail, full latest message."""
        if not messages:
            return {
                "latest_body": "",
                "latest_subject": "",
                "from_addr": "",
                "prior_summary": "",
                "participants": [],
            }
        by_id = {m.message_id: m for m in messages}
        target = by_id.get(reply_to_message_id) or messages[-1]
        prior = [m for m in messages if m.message_id != target.message_id]
        participants = sorted({m.from_addr for m in messages if m.from_addr})
        prior_summary = ""
        if prior:
            bullets: list[str] = []
            for m in prior[-5:]:
                excerpt = (m.body or m.snippet or "").strip().replace("\n", " ")[:200]
                bullets.append(f"- {m.from_addr}: {excerpt}")
            prior_summary = "\n".join(bullets)
        return {
            "latest_body": target.body or target.snippet or "",
            "latest_subject": target.subject,
            "from_addr": target.from_addr,
            "prior_summary": prior_summary,
            "participants": participants,
        }

    def thread_as_text(self, db: Session, user: User, thread_id: str) -> str:
        messages = self.get_thread(db, user, thread_id)
        parts: list[str] = []
        for m in messages:
            parts.append(
                f"From: {m.from_addr}\nSubject: {m.subject}\nDate: {m.date or ''}\n\n{m.body}\n"
            )
        return "\n---\n".join(parts)

    def poll_label_messages(
        self,
        db: Session,
        user: User,
        label: str,
        *,
        newer_than_days: int = 7,
        max_results: int = 100,
        processed_ids: set[str] | None = None,
        exclude_processed: bool = False,
    ) -> list[ParsedEmail]:
        label_part = _label_query_part(label) if label else "in:inbox"
        q = label_part
        if newer_than_days > 0:
            q += f" newer_than:{newer_than_days}d"
        return self.fetch_messages_for_query(
            db,
            user,
            q,
            max_total=max_results,
            processed_ids=processed_ids,
            exclude_processed=exclude_processed,
        )

    def poll_sender_messages(
        self,
        db: Session,
        user: User,
        sender: str,
        *,
        newer_than_days: int = 7,
        max_results: int = 100,
        processed_ids: set[str] | None = None,
        exclude_processed: bool = False,
    ) -> list[ParsedEmail]:
        q = f"from:{sender} newer_than:{newer_than_days}d"
        return self.fetch_messages_for_query(
            db,
            user,
            q,
            max_total=max_results,
            processed_ids=processed_ids,
            exclude_processed=exclude_processed,
        )

    def poll_watched_thread_messages(
        self,
        db: Session,
        user: User,
        thread_id: str,
        *,
        processed_ids: set[str] | None = None,
    ) -> list[ParsedEmail]:
        seen = processed_ids or set()
        messages = self.get_thread(db, user, thread_id)
        return [m for m in messages if m.message_id not in seen]

    def send_message(
        self,
        db: Session,
        user: User,
        *,
        to_addr: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        attachment_bytes: bytes | None = None,
        attachment_name: str | None = None,
    ) -> dict:
        cred = self._get_credential(db, user)
        token = self._refresh_if_needed(db, cred)
        raw = self._build_mime(to_addr, subject, body, attachment_bytes, attachment_name)
        payload: dict = {"raw": base64.urlsafe_b64encode(raw.encode()).decode()}
        if thread_id:
            payload["threadId"] = thread_id
        return self._api(token, "/messages/send", method="POST", body=payload)

    def _build_mime(
        self,
        to_addr: str,
        subject: str,
        body: str,
        attachment_bytes: bytes | None,
        attachment_name: str | None,
    ) -> str:
        if not attachment_bytes:
            lines = [
                f"To: {to_addr}",
                f"Subject: {subject}",
                "Content-Type: text/plain; charset=utf-8",
                "",
                body,
            ]
            return "\r\n".join(lines)
        import email.mime.application
        import email.mime.multipart
        import email.mime.text

        msg = email.mime.multipart.MIMEMultipart()
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))
        part = email.mime.application.MIMEApplication(attachment_bytes)
        part.add_header("Content-Disposition", "attachment", filename=attachment_name or "document.docx")
        msg.attach(part)
        return msg.as_string()

    def poll_inbox(self, db: Session, user: User) -> list[dict]:
        """MSA automation: ingest vendor returns from watched/linked Gmail threads."""
        from app.services.msa_gmail_ingest_service import poll_msa_vendor_threads

        result = poll_msa_vendor_threads(db, user)
        return result.get("ingested", []) + [
            {**item, "auto_created": True} for item in result.get("auto_created", [])
        ]


def mark_message_processed(processed_ids: list[str], message_id: str) -> list[str]:
    updated = list(processed_ids)
    if message_id not in updated:
        updated.append(message_id)
    if len(updated) > _MAX_PROCESSED_IDS:
        updated = updated[-_MAX_PROCESSED_IDS:]
    return updated


def _walk_attachment_parts(
    payload: dict,
    *,
    prefix: str = "",
) -> list[dict]:
    """Collect attachment metadata from a Gmail message MIME tree."""
    found: list[dict] = []
    filename = payload.get("filename") or ""
    att_id = payload.get("body", {}).get("attachmentId")
    if filename and att_id:
        found.append(
            {
                "filename": filename,
                "mime_type": payload.get("mimeType", "application/octet-stream"),
                "attachment_id": att_id,
            }
        )
    for part in payload.get("parts", []):
        found.extend(_walk_attachment_parts(part))
    return found


def list_attachments(message_id: str, payload: dict) -> list[dict]:
    """Return attachment metadata for a Gmail message payload."""
    return _walk_attachment_parts(payload)


def download_attachment(
    message_id: str,
    attachment_id: str,
    token: str,
    svc: GmailService,
) -> bytes:
    att = svc._api(token, f"/messages/{message_id}/attachments/{attachment_id}")
    return base64.urlsafe_b64decode(att["data"] + "==")


def _first_attachment(
    message_id: str, payload: dict, token: str, svc: GmailService
) -> tuple[bytes, str, str] | None:
    attachments = list_attachments(message_id, payload)
    if not attachments:
        return None
    meta = attachments[0]
    data = download_attachment(message_id, meta["attachment_id"], token, svc)
    return data, meta["filename"], meta["mime_type"]


def _is_docx_attachment(filename: str, mime_type: str) -> bool:
    name = (filename or "").lower()
    mime = (mime_type or "").lower()
    return name.endswith(".docx") or "wordprocessingml" in mime


def first_docx_attachment(
    message_id: str, payload: dict, token: str, svc: GmailService
) -> tuple[bytes, str, str] | None:
    """Prefer .docx attachments; fall back to the first attachment."""
    attachments = list_attachments(message_id, payload)
    if not attachments:
        return None
    ordered = sorted(attachments, key=lambda a: (0 if _is_docx_attachment(a["filename"], a["mime_type"]) else 1))
    meta = ordered[0]
    data = download_attachment(message_id, meta["attachment_id"], token, svc)
    return data, meta["filename"], meta["mime_type"]


_gmail: GmailService | None = None


def get_gmail_service() -> GmailService:
    global _gmail
    if _gmail is None:
        _gmail = GmailService()
    return _gmail
