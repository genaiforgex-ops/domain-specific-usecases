"""Password hashing and JWT encode/decode — the auth primitives."""

from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt only ever consumes the first 72 *bytes* of the input; bcrypt >= 4.1
# raises instead of silently truncating, which would surface as a 500 on any
# longer password (create / reset / change). Truncate to 72 bytes ourselves —
# identically on hash and verify so they always agree — on the UTF-8 encoding,
# stripping any partial trailing multibyte char so we never pass invalid bytes.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    while raw:
        try:
            raw.decode("utf-8")
            break
        except UnicodeDecodeError:
            raw = raw[:-1]  # drop a byte from a split multibyte char at the boundary
    return raw


def hash_password(password: str) -> str:
    return pwd_context.hash(_prepare(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_prepare(plain), hashed)


def create_access_token(
    subject: str,
    *,
    roles: list[str] | None = None,
    active_role: str | None = None,
) -> str:
    """Mint the app's own session JWT.

    ``roles`` is the set of role codes granted this identity, and
    ``active_role`` is the one the user is currently acting as. Both are carried
    in the signed token so role-switching needs no server-side store.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict = {"sub": subject, "exp": expire}
    if roles is not None:
        payload["roles"] = roles
    if active_role is not None:
        payload["arole"] = active_role
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
