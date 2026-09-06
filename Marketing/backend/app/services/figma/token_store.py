"""Per-user Figma OAuth token storage (DB-backed).

The mcp_client works with a plain ``oauth`` dict of the shape
``{"client_info": {...}, "tokens": {...}}``. This module persists that dict
against a user in the ``figma_credentials`` table, so each Designer's Figma
connection is their own — loaded, refreshed, and cleared independently.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.figma_credential import FigmaCredential


def load(db: Session, user_id: uuid.UUID) -> dict | None:
    """The user's stored oauth (``{client_info, tokens}``) plus ``handle``, or
    None if they haven't connected Figma."""
    cred = db.get(FigmaCredential, user_id)
    if cred is None:
        return None
    return {"client_info": cred.client_info, "tokens": cred.tokens, "handle": cred.figma_handle}


def save(db: Session, user_id: uuid.UUID, oauth: dict, handle: str | None = None) -> None:
    """Upsert the user's oauth. Reassigns the JSON columns wholesale so SQLAlchemy
    always detects the change (e.g. after a token refresh)."""
    cred = db.get(FigmaCredential, user_id)
    if cred is None:
        cred = FigmaCredential(
            user_id=user_id,
            client_info=oauth["client_info"],
            tokens=oauth["tokens"],
            figma_handle=handle,
        )
        db.add(cred)
    else:
        cred.client_info = dict(oauth["client_info"])
        cred.tokens = dict(oauth["tokens"])
        if handle is not None:
            cred.figma_handle = handle
    db.commit()


def clear(db: Session, user_id: uuid.UUID) -> bool:
    """Delete the user's Figma connection. Returns True if one existed."""
    cred = db.get(FigmaCredential, user_id)
    if cred is None:
        return False
    db.delete(cred)
    db.commit()
    return True
