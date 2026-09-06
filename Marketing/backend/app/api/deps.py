"""Shared FastAPI dependencies — resolving the current user from the session.

The session lives in an httpOnly cookie (browsers); an `Authorization: Bearer`
header is accepted as a fallback for curl / Postman. Cookie is checked first.
"""

import uuid

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.core.session import SESSION_COOKIE_NAME
from app.database import get_db
from app.models.user import User

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _read_token(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = _read_token(request)
    if not token:
        raise _credentials_error
    try:
        payload = decode_token(token)
        sub: str | None = payload.get("sub")
        if sub is None:
            raise _credentials_error
        user_id = uuid.UUID(sub)
    except (JWTError, ValueError):
        raise _credentials_error

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_error

    granted = [str(r) for r in (payload.get("roles") or [])]
    user.session_roles = granted or [user.role]
    user.active_role = user.role
    return user


def get_current_admin(current: User = Depends(get_current_user)) -> User:
    if current.role != "AD":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return current
