"""Resolve `@`-mention / attachment references into a grounded context block.

Reuses the existing LegalOS services rather than reimplementing retrieval:
  - MSA versions   → the same access-checked latest-version logic the legacy
                     LegalBot uses (see api/legal_bot.py).
  - Gmail threads  → gmail_service.thread_as_text (already OAuth-wired).
  - Attachments    → the in-process attachment store.
  - KB entries     → KnowledgeBaseEntry rows.

The assembled block is prepended to the user's message before the model call,
so the agent grounds its answer in exactly what the user attached. The total is
truncated to ``max_chars`` to protect the context window.

Also returns chunk-level ``Source`` dicts so attached materials appear in
References and support the Evidence panel (recorded by the pipeline after
``start_collection``).
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.msa_version import MSADocumentVersion
from app.models.playbook import KnowledgeBaseEntry
from app.models.user import User
from app.orchestrator.attachments import store as attachment_store
from app.orchestrator.models import ContextRef
from app.orchestrator.sources import clip_chunk_text, clip_snippet, make_chunk_id
from app.services.gmail_service import get_gmail_service
from app.services.msa_access import ACCESS_VIEW, load_tracker_with_access

logger = logging.getLogger("legalos.orchestrator")

_PER_SOURCE_CHARS = 50000
_CHUNK_CHARS = 1800
_MAX_CHUNKS_PER_REF = 6
# Rough page estimate for uploaded text (matches frontend ~50 lines/page heuristic).
_CHARS_PER_PAGE = 2800


def _msa_version_text(db: Session, tracker_id: int, version_id: int | None) -> str:
    if version_id is not None:
        version = db.get(MSADocumentVersion, version_id)
        if version is None or version.tracker_id != tracker_id:
            return ""
        return (version.extracted_text or "")[:_PER_SOURCE_CHARS]
    row = db.execute(
        select(MSADocumentVersion)
        .where(
            MSADocumentVersion.tracker_id == tracker_id,
            MSADocumentVersion.source.in_(["legal_redline", "legal_base"]),
        )
        .order_by(MSADocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (row.extracted_text or "")[:_PER_SOURCE_CHARS] if row else ""


def _split_chunks(text: str) -> list[tuple[int, str]]:
    """Split text into ~1–2k char windows (paragraph-aware), capped per ref."""
    raw = (text or "").strip()
    if not raw:
        return []
    paragraphs = re.split(r"\n\s*\n", raw)
    windows: list[tuple[int, str]] = []
    buf = ""
    buf_start = 0
    cursor = 0
    for para in paragraphs:
        if not para.strip():
            cursor += len(para) + 2
            continue
        # Approximate offset of this paragraph in the original string.
        idx = raw.find(para, cursor)
        if idx < 0:
            idx = cursor
        if buf and len(buf) + len(para) + 2 > _CHUNK_CHARS:
            windows.append((buf_start, buf.strip()))
            if len(windows) >= _MAX_CHUNKS_PER_REF:
                return windows
            buf = para
            buf_start = idx
        else:
            if not buf:
                buf_start = idx
            buf = f"{buf}\n\n{para}" if buf else para
        cursor = idx + len(para)
    if buf.strip() and len(windows) < _MAX_CHUNKS_PER_REF:
        windows.append((buf_start, buf.strip()))
    if not windows and raw:
        # Fallback: fixed windows
        for i in range(0, min(len(raw), _CHUNK_CHARS * _MAX_CHUNKS_PER_REF), _CHUNK_CHARS):
            windows.append((i, raw[i : i + _CHUNK_CHARS]))
            if len(windows) >= _MAX_CHUNKS_PER_REF:
                break
    return windows


def resolve_context(
    db: Session,
    user: User,
    refs: list[ContextRef],
    *,
    max_chars: int,
) -> tuple[str, list[dict]]:
    """Return ``(context_block, source_dicts)`` for the given references.

    Access is enforced per source (MSA trackers via ``load_tracker_with_access``;
    attachments scoped to the owning user). A source the user may not see is
    skipped with a log line rather than failing the whole turn.

    The context block is numbered ``1. …`` matching the returned source list so
    the model can cite ``[n]`` in References order (attachments first).
    """
    if not refs:
        return "", []

    numbered_lines: list[str] = []
    sources: list[dict] = []
    cite_n = 0

    def _emit(
        *,
        header: str,
        body: str,
        title: str,
        attachment_id: str | None = None,
        label: str | None = None,
        site: str | None = None,
    ) -> None:
        nonlocal cite_n
        for offset, chunk in _split_chunks(body):
            cite_n += 1
            chunk_body = clip_chunk_text(chunk)
            page = max(1, offset // _CHARS_PER_PAGE + 1)
            sources.append(
                {
                    "kind": "attachment",
                    "title": title,
                    "url": None,
                    "snippet": clip_snippet(chunk),
                    "chunk_text": chunk_body,
                    "chunk_id": make_chunk_id(
                        "att",
                        attachment_id or title,
                        str(offset),
                        chunk_body[:240],
                    ),
                    "site": site,
                    "storage_key": None,
                    "page": page,
                    "attachment_id": attachment_id,
                    "label": label or title,
                }
            )
            # The page is an estimate from the character offset, so it is kept on the
            # Source (for the Evidence jump) but not shown to the model: it used to
            # echo "(approx. page 3)" into the answer, which reads as a real citation.
            numbered_lines.append(f"{cite_n}. {header}\n{chunk_body}")

    for ref in refs:
        try:
            if ref.kind == "msa_version" and ref.tracker_id is not None:
                load_tracker_with_access(ref.tracker_id, user, db, min_level=ACCESS_VIEW)
                text = _msa_version_text(db, ref.tracker_id, ref.version_id)
                if text:
                    label = ref.label or f"MSA tracker #{ref.tracker_id}"
                    _emit(
                        header=f"[Document: {label}]",
                        body=text,
                        title=label,
                        label=label,
                        site="MSA",
                    )

            elif ref.kind == "gmail_thread" and ref.gmail_thread_id:
                text = get_gmail_service().thread_as_text(db, user, ref.gmail_thread_id)
                if text:
                    label = ref.label or ref.gmail_thread_id
                    _emit(
                        header=f"[Email thread: {label}]",
                        body=text,
                        title=label,
                        label=label,
                        site="Gmail",
                    )

            elif ref.kind == "attachment" and ref.attachment_id:
                att = attachment_store.get(ref.attachment_id, user.id)
                if att:
                    _emit(
                        header=f"[Attached file: {att.filename}]",
                        body=att.text[:_PER_SOURCE_CHARS],
                        title=att.filename,
                        attachment_id=ref.attachment_id,
                        label=att.filename,
                        site="Upload",
                    )

            elif ref.kind == "kb_entry" and ref.kb_entry_id is not None:
                entry = db.get(KnowledgeBaseEntry, ref.kb_entry_id)
                if entry is not None:
                    body = getattr(entry, "answer", None) or getattr(entry, "content", "") or ""
                    title = getattr(entry, "topic", None) or getattr(entry, "title", "") or "KB"
                    _emit(
                        header=f"[Knowledge base: {title}]",
                        body=str(body)[:_PER_SOURCE_CHARS],
                        title=str(title),
                        label=str(title),
                        site="KB",
                    )
        except Exception as exc:  # noqa: BLE001 — skip a bad source, keep the turn alive
            logger.warning("Skipping context ref %s: %s", ref.kind, exc)

    if not numbered_lines:
        return "", []

    preamble = (
        "Attached / mentioned materials (cite inline as [n] matching these numbers; "
        "they appear first in References):\n"
    )
    combined = preamble + "\n\n---\n\n".join(numbered_lines)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n[context truncated]"
    return combined, sources
