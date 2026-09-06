"""Password hashing and JWT access tokens.

The single place that knows how a password becomes a hash and how a login turns
into a signed token. Everything else (endpoints, adapters) calls these helpers so
the crypto choices live in one file.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Response
from jose import JWTError, jwt

from app.core.config import get_settings

ALGORITHM = "HS256"

# App-specific cookie name so local multi-app demos don't clobber each other.
SESSION_COOKIE_NAME = "genaiforge_session"

# bcrypt only considers the first 72 bytes of a password; longer inputs raise on
# newer bcrypt releases, so truncate to that boundary before hashing/verifying.
_BCRYPT_MAX_BYTES = 72


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/legacy hash — treat as a failed login rather than crashing.
        return False


def create_access_token(subject_email: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject_email, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    """Return the subject email if the token is valid and unexpired, else None."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    email = payload.get("sub")
    return email if isinstance(email, str) else None


def set_session_cookie(response: Response, token: str) -> None:
    """Put the app JWT in an httpOnly cookie.

    The cookie always carries our HS256 app token. SameSite=Lax mitigates CSRF
    for same-site browser clients.
    """
    settings = get_settings()
    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=max_age,
        samesite="lax",
        secure=not settings.is_local_dev,  # False only for local http
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
