"""HMAC-signed, expiring tokens for the email approval links.

An approver clicks Approve / Request changes straight from their inbox — the
link carries a signed token identifying the brief and the approver. The token is
self-contained (no server-side state): we verify the signature and expiry, then
resolve the brief + approver and record the lane decision through the normal
``brief_service.approval_signoff`` path.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.config import settings

# How long an approval link stays valid. Approval windows run longer than a
# transactional OTP, so this is generous — a week.
_DEFAULT_TTL_SEC = 60 * 60 * 24 * 7


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _secret() -> bytes:
    """The HMAC key. Refuses to sign or verify with an empty one.

    HMAC accepts a zero-length key perfectly happily, so an unset secret would not
    fail — it would quietly sign every approval link and OTP with a key an attacker
    can guess, letting anyone forge an approval. Loud failure is the only safe
    behaviour; `check_configured()` surfaces it at startup instead of mid-click.
    """
    secret = settings.email.approval_token_secret
    if not secret:
        raise RuntimeError(
            "EMAIL_APPROVAL_TOKEN_SECRET is not set — refusing to sign approval "
            "tokens with an empty key."
        )
    return secret.encode("utf-8")


def check_configured() -> None:
    """Raise if approval links can't be signed safely. Called at startup."""
    _secret()


def sign_payload(payload: dict[str, Any], expires_in_sec: int = _DEFAULT_TTL_SEC) -> str:
    body = {**payload, "exp": int(time.time()) + expires_in_sec}
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def verify_token(token: str) -> dict[str, Any]:
    """Return the token payload, or raise ValueError if it's tampered/expired."""
    try:
        p_raw, s_raw = token.split(".", 1)
        body = _unb64(p_raw)
        sig = _unb64(s_raw)
        expected = hmac.new(_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid signature")
        payload = json.loads(body.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token expired")
        return payload
    except ValueError:
        raise
    except Exception as e:  # malformed base64 / json / split
        raise ValueError("Invalid token") from e


# ── One-time codes (OTP) ─────────────────────────────────────────────────────
# The approver clicks Approve/Request changes → we email a 6-digit code and carry
# its hash inside a short-lived signed token (never the code itself). On submit we
# hash the typed code and compare. The hash uses the server secret, so the code
# can't be brute-forced from the token without it — no DB state needed.


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return hmac.new(_secret(), otp.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(otp: str, otp_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp), otp_hash)


def mask_email(email: str) -> str:
    """a***e@domain — enough to recognize your own address, not to reveal it."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    masked = f"{local[0]}***{local[-1]}" if len(local) > 2 else f"{local[:1]}***"
    return f"{masked}@{domain}"


def action_urls(brief_id: str, approver_id: str) -> tuple[str, str]:
    """(approve_url, request_changes_url) for one approver on one brief."""
    token = sign_payload({"brief_id": str(brief_id), "approver_id": str(approver_id)})
    base = settings.email.api_base_url.rstrip("/")
    return (
        f"{base}/api/approvals/action?decision=approve&token={token}",
        f"{base}/api/approvals/action?decision=request_changes&token={token}",
    )
