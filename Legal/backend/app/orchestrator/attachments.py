"""In-process + durable store for documents attached to a chat turn.

Parsed text is persisted in Postgres (``chat_attachments``) so uploads survive
process restarts and multi-worker replicas. An in-memory LRU caches hot reads.
``ContextRef`` of kind ``attachment`` is unchanged.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from app.database import SessionLocal
from app.models.chat import ChatAttachment

_MAX_MEMORY = 256


@dataclass
class Attachment:
    attachment_id: str
    user_id: int
    filename: str
    text: str


class _AttachmentStore:
    def __init__(self) -> None:
        self._items: "OrderedDict[str, Attachment]" = OrderedDict()
        self._lock = threading.Lock()

    def _cache_put(self, att: Attachment) -> None:
        with self._lock:
            self._items[att.attachment_id] = att
            self._items.move_to_end(att.attachment_id)
            while len(self._items) > _MAX_MEMORY:
                self._items.popitem(last=False)

    def put(self, user_id: int, filename: str, text: str) -> Attachment:
        att = Attachment(
            attachment_id=uuid.uuid4().hex,
            user_id=user_id,
            filename=filename,
            text=text,
        )
        db = SessionLocal()
        try:
            db.add(
                ChatAttachment(
                    attachment_id=att.attachment_id,
                    user_id=user_id,
                    filename=filename,
                    text=text,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        self._cache_put(att)
        return att

    def get(self, attachment_id: str, user_id: int) -> Attachment | None:
        """Fetch an attachment, scoped to the owning user (no cross-user reads)."""
        with self._lock:
            cached = self._items.get(attachment_id)
        if cached is not None:
            if cached.user_id != user_id:
                return None
            with self._lock:
                self._items.move_to_end(attachment_id)
            return cached

        db = SessionLocal()
        try:
            row = db.get(ChatAttachment, attachment_id)
            if row is None or row.user_id != user_id:
                return None
            att = Attachment(
                attachment_id=row.attachment_id,
                user_id=row.user_id,
                filename=row.filename,
                text=row.text,
            )
            self._cache_put(att)
            return att
        finally:
            db.close()


store = _AttachmentStore()
