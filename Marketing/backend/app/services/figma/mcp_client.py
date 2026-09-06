"""Figma MCP client — the server-side seam to https://mcp.figma.com/mcp.

The Figma REST API is read-only for node creation, so banners are written through
the remote MCP (`use_figma`, `create_new_file`, `upload_assets`), which runs code
against the Figma Plugin API. Auth reuses the Claude Code / Figma OAuth token that
`generate_banners.py --login` writes to ~/.config/figma_agent/oauth.json — the
backend runs as the same machine user, so it reads that token directly.

Unlike the standalone script, this module never opens a browser: a server can't
do interactive OAuth. If the token is missing or refresh fails it raises
`FigmaAuthError`, and the caller surfaces a clear "re-authenticate" message.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

from app.config import settings

PROTOCOL_VERSION = "2025-06-18"
JSON_CT = "application/json"
_AS_METADATA_URL = "https://mcp.figma.com/.well-known/oauth-authorization-server"
OAUTH_SCOPE = "mcp:connect"


class FigmaAuthError(RuntimeError):
    """The Figma OAuth token is missing or could not be refreshed."""


class FigmaMCPError(RuntimeError):
    """A Figma MCP call failed (transport or tool-level error)."""


# Status checks must return quickly (they gate the UI). Bound their MCP round-trips
# so a slow/unreachable Figma reports "disconnected" in seconds, not minutes.
_STATUS_TIMEOUT = 20


def _post(url: str, headers: dict, body, form: bool = False, timeout: int = 180):
    data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")


def _extract_jsonrpc(raw: str, want_id):
    """MCP responses arrive as JSON or as an SSE stream of `data:` lines."""
    raw = raw.strip()
    msgs: list = []
    if raw[:1] in "{[":
        try:
            msgs.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    else:
        for block in re.split(r"\n\s*\n", raw):
            datas = [ln[5:].lstrip() for ln in block.splitlines() if ln.startswith("data:")]
            if datas:
                try:
                    msgs.append(json.loads("".join(datas)))
                except json.JSONDecodeError:
                    pass
    for m in msgs:
        if isinstance(m, dict) and m.get("id") == want_id:
            return m
    return msgs[-1] if msgs else None


def _refresh_access_token(oauth: dict, save=None) -> str | None:
    """Refresh the access token in place using the stored refresh token. If a
    ``save`` callback is given, persist the updated oauth (e.g. back to the DB)."""
    try:
        with urllib.request.urlopen(_AS_METADATA_URL, timeout=30) as r:
            meta = json.loads(r.read().decode())
        token_endpoint = meta.get("token_endpoint")
    except Exception:  # noqa: BLE001 — treat any discovery failure as "can't refresh"
        return None
    if not token_endpoint:
        return None

    ci, tok = oauth["client_info"], oauth["tokens"]
    status, _, text = _post(
        token_endpoint,
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": JSON_CT},
        {
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": ci["client_id"],
            "client_secret": ci.get("client_secret", ""),
        },
        form=True,
    )
    if status != 200:
        return None
    new = json.loads(text)
    oauth["tokens"]["access_token"] = new["access_token"]
    if new.get("refresh_token"):
        oauth["tokens"]["refresh_token"] = new["refresh_token"]
    if save is not None:
        save(oauth)
    return new["access_token"]


class FigmaMCP:
    """A minimal JSON-RPC client for the remote Figma MCP, with one MCP session."""

    def __init__(self, token: str):
        self.token = token
        self.session_id: str | None = None
        self._id = 0

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": JSON_CT,
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def initialize(self, timeout: int = 180) -> None:
        rid = self._next_id()
        status, headers, text = _post(
            settings.figma_mcp_url,
            self._headers(),
            {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "genaiforge-marketing", "version": "1.0.0"},
                },
            },
            timeout=timeout,
        )
        if status == 401:
            raise PermissionError("401 on initialize")
        sid = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if status >= 400:
            raise FigmaMCPError(f"initialize failed HTTP {status}: {text[:400]}")
        _post(
            settings.figma_mcp_url,
            self._headers(),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=timeout,
        )

    def call_tool(self, name: str, arguments: dict, timeout: int = 180) -> dict:
        rid = self._next_id()
        status, _, text = _post(
            settings.figma_mcp_url,
            self._headers(),
            {
                "jsonrpc": "2.0",
                "id": rid,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            timeout=timeout,
        )
        if status == 401:
            raise PermissionError("401 on tools/call")
        if status >= 400:
            raise FigmaMCPError(f"{name} failed HTTP {status}: {text[:600]}")
        msg = _extract_jsonrpc(text, rid)
        if not msg:
            raise FigmaMCPError(f"{name}: empty response")
        if "error" in msg:
            raise FigmaMCPError(f"{name}: {json.dumps(msg['error'])[:600]}")
        result = msg.get("result", {})
        if result.get("isError"):
            raise FigmaMCPError(f"{name} tool error: {_result_text(result)[:600] or result}")
        return msg


def connect(oauth: dict | None, save=None, timeout: int = 180) -> FigmaMCP:
    """Given a user's OAuth dict, refresh it if the session is rejected, and return
    a ready (initialized) MCP client. Raises FigmaAuthError if auth is unavailable.
    ``save`` persists a refreshed token (e.g. back to the user's DB row). ``timeout``
    bounds the MCP handshake — kept short for status checks so the UI can't hang."""
    if not oauth or not oauth.get("tokens", {}).get("access_token"):
        raise FigmaAuthError("Figma is not connected. Use “Connect Figma” to authorize.")
    client = FigmaMCP(oauth["tokens"]["access_token"])
    try:
        client.initialize(timeout=timeout)
        return client
    except PermissionError:
        token = _refresh_access_token(oauth, save)
        if not token:
            raise FigmaAuthError(
                "Figma authorization expired and could not be refreshed. "
                "Use “Connect Figma” to reconnect."
            ) from None
        client = FigmaMCP(token)
        client.initialize(timeout=timeout)
        return client


# ── In-app OAuth (PKCE) ──────────────────────────────────────────────────────
# Figma grants the `mcp:connect` scope only to approved client names, so dynamic
# registration uses settings.figma_oauth_client_name. The backend hosts the
# redirect (settings.figma_redirect_uri) instead of a throwaway localhost server.


def _auth_metadata() -> dict:
    with urllib.request.urlopen(_AS_METADATA_URL, timeout=30) as r:
        return json.loads(r.read().decode())


def _register_client(meta: dict, redirect_uri: str) -> dict:
    status, _, text = _post(
        meta["registration_endpoint"],
        {"Content-Type": JSON_CT, "Accept": JSON_CT},
        {
            "redirect_uris": [redirect_uri],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": OAUTH_SCOPE,
            "client_name": settings.figma_oauth_client_name,
        },
    )
    if status >= 400:
        raise FigmaAuthError(f"Figma client registration failed (HTTP {status}).")
    return json.loads(text)


def begin_login(redirect_uri: str) -> dict:
    """Start a PKCE login. Returns the authorize URL plus the per-attempt secrets
    the caller must hold until the redirect comes back (keyed by `state`)."""
    meta = _auth_metadata()
    client_info = _register_client(meta, redirect_uri)
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state = secrets.token_urlsafe(16)
    authorize_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(
        {
            "client_id": client_info["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": OAUTH_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return {
        "authorize_url": authorize_url,
        "state": state,
        "verifier": verifier,
        "client_info": client_info,
        "token_endpoint": meta["token_endpoint"],
    }


def complete_login(
    code: str, verifier: str, client_info: dict, token_endpoint: str, redirect_uri: str
) -> dict:
    """Exchange the authorization code for tokens and return the oauth dict
    (``{client_info, tokens}``) for the caller to persist against the user."""
    status, _, text = _post(
        token_endpoint,
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": JSON_CT},
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_info["client_id"],
            "client_secret": client_info.get("client_secret", ""),
            "code_verifier": verifier,
        },
        form=True,
    )
    if status >= 400:
        raise FigmaAuthError(f"Figma token exchange failed (HTTP {status}).")
    return {"client_info": client_info, "tokens": json.loads(text)}


def connection_status(oauth: dict | None, save=None) -> dict:
    """Report whether a user's Figma is connected, refreshing the token if needed.

    Returns {"connected": bool, "handle": str | None, "reason": str | None}."""
    if not oauth or not oauth.get("tokens", {}).get("access_token"):
        return {"connected": False, "handle": None, "reason": "not_connected"}
    # A status check must be snappy — bound the handshake/whoami so a slow or
    # unreachable Figma MCP reports "disconnected" fast instead of hanging the UI.
    try:
        client = connect(oauth, save, timeout=_STATUS_TIMEOUT)
    except FigmaAuthError as e:
        return {"connected": False, "handle": None, "reason": str(e)}
    except Exception:  # noqa: BLE001 — any transport hiccup → report disconnected
        return {"connected": False, "handle": None, "reason": "unreachable"}

    handle = None
    try:
        info = _tool_json(client.call_tool("whoami", {}, timeout=_STATUS_TIMEOUT))
        handle = info.get("handle") or info.get("email")
    except Exception:  # noqa: BLE001 — connected is what matters; handle is cosmetic
        pass
    return {"connected": True, "handle": handle, "reason": None}


def _result_text(result: dict) -> str:
    """Concatenate the text blocks of an MCP tool result (for error surfacing)."""
    parts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    return " ".join(p for p in parts if p).strip()


def _tool_json(resp: dict) -> dict:
    """Parse the structured payload from an MCP tool result.

    Prefers the first JSON text block, then falls back to `structuredContent`
    (some Figma tools return only the latter)."""
    result = resp.get("result", {})
    for c in result.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except (json.JSONDecodeError, TypeError):
                continue
    sc = result.get("structuredContent")
    return sc if isinstance(sc, dict) else {}


def create_file(client: FigmaMCP, file_name: str) -> dict:
    """Create a new blank Figma design file in the configured plan.

    Returns {"file_key": str, "file_url": str}."""
    resp = client.call_tool(
        "create_new_file",
        {
            "fileName": file_name,
            "planKey": settings.figma_plan_key,
            "editorType": "design",
        },
    )
    data = _tool_json(resp)
    file_key = data.get("file_key") or data.get("fileKey")
    file_url = data.get("file_url") or data.get("fileUrl")
    if not file_key:
        raise FigmaMCPError(f"create_new_file returned no file key: {data}")
    return {"file_key": file_key, "file_url": file_url or f"https://www.figma.com/design/{file_key}"}


def upload_image(client: FigmaMCP, file_key: str, png_bytes: bytes, mime: str = "image/png") -> str:
    """Upload one image into the file and return its Figma imageHash.

    Two steps: ask the MCP for a single-use submit URL, then POST the raw bytes to
    it. The image is auto-placed on the page (a throwaway frame we clear at render
    time), and the POST response carries the imageHash we fill banners with."""
    resp = client.call_tool("upload_assets", {"fileKey": file_key, "count": 1})
    info = _tool_json(resp)
    uploads = info.get("uploads") or []
    if not uploads or not uploads[0].get("submitUrl"):
        raise FigmaMCPError(f"upload_assets returned no submit URL: {info}")

    submit_url = uploads[0]["submitUrl"]
    req = urllib.request.Request(
        submit_url,
        data=png_bytes,
        method="POST",
        headers={"Content-Type": mime, "Authorization": f"Bearer {client.token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise FigmaMCPError(f"image upload failed HTTP {e.code}: {e.read().decode()[:400]}") from e
    image_hash = body.get("imageHash")
    if not image_hash:
        raise FigmaMCPError(f"image upload returned no imageHash: {body}")
    return image_hash


def render_creative(client: FigmaMCP, file_key: str, code: str, description: str) -> dict:
    """Run one banner-render batch (all creatives × one size) via use_figma."""
    resp = client.call_tool(
        "use_figma",
        {
            "fileKey": file_key,
            "code": code,
            "description": description,
            "skillNames": "resource:figma-use",
        },
    )
    return _tool_json(resp)
