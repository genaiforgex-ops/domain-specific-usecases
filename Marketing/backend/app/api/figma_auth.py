"""Figma connection routes — in-app OAuth so the Designer can authorize Figma
without touching a terminal.

Flow: the SPA calls POST /connect → gets a Figma authorize URL → opens it in a new
tab → the user approves → Figma redirects to GET /callback (no app auth — it's a
browser redirect) → the backend exchanges the code and saves the token. The SPA
polls GET /status until it flips to connected.

Auth is per-user: the initiating user is remembered against the OAuth ``state``,
and the token is saved to THAT user's ``figma_credentials`` row. Every user's
connection — and the export that uses it — is their own; nothing is shared.
"""

import html
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.figma import mcp_client, token_store

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/figma", tags=["figma"])

DESIGNER_ROLE = "DS"

# Per-attempt PKCE secrets, keyed by OAuth `state`. Single-process dev server, so
# in-memory is fine; entries are popped on callback and capped to avoid growth.
_PENDING: dict[str, dict] = {}
_PENDING_CAP = 16


def _callback_page(title: str, message: str, ok: bool) -> HTMLResponse:
    color = "#1CBABA" if ok else "#d23"
    home = html.escape(settings.figma_post_login_redirect)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;background:#0B0C10;color:#fff;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{text-align:center;max-width:32rem;padding:2.5rem}}
h2{{color:{color};margin:0 0 .5rem}} a{{color:#B8956C}}</style></head>
<body><div class="card"><h2>{html.escape(title)}</h2>
<p>{html.escape(message)}</p>
<p>You can close this tab and return to <a href="{home}">GenAIForge Marketing</a>.</p>
<script>setTimeout(function(){{window.close()}},1500)</script>
</div></body></html>"""
    return HTMLResponse(content=body, status_code=status.HTTP_200_OK)


@router.get("/status")
def figma_status(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Whether THIS user's Figma is connected (token present and accepted), with
    the handle. Persists a refreshed token / freshly-read handle back to their row."""
    oauth = token_store.load(db, user.id)
    result = mcp_client.connection_status(
        oauth, save=lambda o: token_store.save(db, user.id, o)
    )
    if oauth and result.get("connected") and result.get("handle"):
        token_store.save(db, user.id, oauth, handle=result["handle"])
    return result


@router.post("/connect")
def figma_connect(user: User = Depends(get_current_user)) -> dict:
    """Begin an in-app Figma login. Returns the authorize URL to open in a new tab."""
    if user.role != DESIGNER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Designers only")
    try:
        login = mcp_client.begin_login(settings.figma_redirect_uri)
    except mcp_client.FigmaAuthError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    # Bound the pending map; drop the oldest if it somehow fills (abandoned logins).
    if len(_PENDING) >= _PENDING_CAP:
        _PENDING.pop(next(iter(_PENDING)), None)
    # Remember WHO started this login so the callback saves the token to them.
    _PENDING[login["state"]] = {
        "user_id": user.id,
        "verifier": login["verifier"],
        "client_info": login["client_info"],
        "token_endpoint": login["token_endpoint"],
    }
    return {"authorize_url": login["authorize_url"]}


@router.delete("/connect")
def figma_disconnect(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Disconnect THIS user's Figma account (delete their stored token)."""
    if user.role != DESIGNER_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Designers only")
    removed = token_store.clear(db, user.id)
    return {"disconnected": removed}


@router.get("/callback", response_class=HTMLResponse)
def figma_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Catch the Figma redirect, exchange the code, and persist the token to the
    user who started this login (looked up by ``state``)."""
    if error:
        return _callback_page("Figma authorization declined", f"Figma returned: {error}", ok=False)
    if not code or not state:
        return _callback_page("Couldn't connect Figma", "Missing authorization code.", ok=False)

    pending = _PENDING.pop(state, None)
    if pending is None:
        return _callback_page(
            "Couldn't connect Figma",
            "This login link has expired or was already used. Start again from the app.",
            ok=False,
        )

    try:
        oauth = mcp_client.complete_login(
            code=code,
            verifier=pending["verifier"],
            client_info=pending["client_info"],
            token_endpoint=pending["token_endpoint"],
            redirect_uri=settings.figma_redirect_uri,
        )
    except mcp_client.FigmaAuthError as e:
        logger.warning("Figma token exchange failed: %s", e)
        return _callback_page("Couldn't connect Figma", str(e), ok=False)

    # Best-effort handle for display; the token is valid regardless.
    handle = mcp_client.connection_status(oauth).get("handle")
    token_store.save(db, pending["user_id"], oauth, handle=handle)
    logger.info("Figma connected for user %s (%s)", pending["user_id"], handle or "?")

    return _callback_page("Figma connected", "Your Figma account is now linked.", ok=True)
