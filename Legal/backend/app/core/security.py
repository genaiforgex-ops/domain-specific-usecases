from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings

# User-facing auth messages (also returned on 401 so the SPA can show them).
MSG_IDLE_EXPIRED = "Your session expired due to inactivity. Please sign in again."
MSG_ABSOLUTE_EXPIRED = (
    "Your session ended after the maximum allowed time. Please sign in again."
)
MSG_INVALID = "Invalid session. Please sign in again."


def hash_password(password: str) -> str:
    # bcrypt hard-limits inputs to 72 bytes; truncate to match legacy passlib behaviour.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pw = plain.encode("utf-8")[:72]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _as_utc(value: datetime | int | float) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def session_started_at_from_claims(payload: dict[str, Any]) -> datetime:
    """Original login/auth time used for the absolute session cap."""
    raw = payload.get("auth_time", payload.get("iat"))
    if raw is None:
        return datetime.now(timezone.utc)
    return _as_utc(raw)


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    *,
    session_started_at: datetime | None = None,
) -> str:
    """Mint a bearer JWT with sliding idle expiry + absolute session cap.

    ``auth_time`` (OIDC-style) is preserved across refreshes so idle sliding
    cannot extend the session past ``access_token_absolute_hours``.
    """
    now = datetime.now(timezone.utc)
    started = _as_utc(session_started_at) if session_started_at else now
    absolute_end = started + timedelta(hours=settings.access_token_absolute_hours)
    idle_end = now + timedelta(minutes=settings.access_token_expire_minutes)
    exp = min(idle_end, absolute_end)
    if exp <= now:
        # Caller should have rejected already; fail closed.
        raise ValueError(MSG_ABSOLUTE_EXPIRED)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": exp,
        "auth_time": int(started.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_file_download_token(user_id: int, storage_key: str) -> str:
    """Short-lived token for ONLYOFFICE (or other servers) to fetch a stored file."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=4),
        "purpose": "file_download",
        "storage_key": storage_key,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token if isinstance(token, str) else token.decode("utf-8")


def create_invite_token(user_id: int, email: str) -> str:
    """Signed, expiring token embedded in an invite link. Carries purpose="invite"
    so the accept endpoint can reject tokens minted for anything else."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.invite_token_expire_hours),
        "purpose": "invite",
        "email": email,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError as exc:
        # Prefer a clearer message when we can peek at purpose without verifying exp.
        try:
            unverified = jwt.get_unverified_claims(token)
            if unverified.get("purpose") == "invite":
                raise ValueError("This invite link is invalid or has expired.") from exc
        except Exception:  # noqa: BLE001
            pass
        raise ValueError(MSG_IDLE_EXPIRED) from exc
    except JWTError as exc:
        raise ValueError(MSG_INVALID) from exc

    purpose = payload.get("purpose")
    if purpose in ("invite", "file_download"):
        return payload

    # Enforce absolute cap even if the idle window was refreshed.
    started = session_started_at_from_claims(payload)
    absolute_end = started + timedelta(hours=settings.access_token_absolute_hours)
    if datetime.now(timezone.utc) >= absolute_end:
        raise ValueError(MSG_ABSOLUTE_EXPIRED)
    return payload


def token_expires_in_seconds(payload: dict[str, Any] | None = None) -> int:
    """Seconds until the current idle deadline (for TokenResponse.expires_in)."""
    if payload and payload.get("exp") is not None:
        exp = _as_utc(payload["exp"])
        return max(0, int((exp - datetime.now(timezone.utc)).total_seconds()))
    return settings.access_token_expire_minutes * 60
