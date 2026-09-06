"""Shared FastAPI dependencies — current user resolution and permission gating."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rbac import Permission, Role, has_permission
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# App-specific cookie name — deliberately not a generic "access_token" or
# "session". Browser cookies are scoped by (domain, path, name) only, NOT by
# port, so several JFS apps running on localhost:<different ports> in dev
# would otherwise silently overwrite each other's session cookie under one
# shared name.
SESSION_COOKIE_NAME = "legalos_session"
_IS_PROD = settings.legalos_env.strip().lower() not in ("dev", "local", "development")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.access_token_absolute_hours * 3600,
        expires=settings.access_token_absolute_hours * 3600,
        samesite="lax",
        secure=_IS_PROD,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def get_current_user(
    request: Request,
    token: str | None = Depends(_oauth2_scheme),
    token_query: str | None = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    # Session cookie first (browser SPA), then Bearer header / ?token= as a
    # documented fallback for non-browser API clients and any lingering
    # direct-file links that predate the cookie.
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        token = cookie_token
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
    if not token and token_query:
        token = token_query
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user")
    return user


def require_permission(*permissions: Permission):
    """Return a dependency that ensures the caller has at least one of the given
    permissions for their role.
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        try:
            role = Role(user.role)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unknown role") from exc
        if not any(has_permission(role, p) for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' lacks permission for this action",
            )
        return user

    return dependency


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """Gate an endpoint to Super Admins only (stricter than any permission)."""
    if user.role != Role.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a Super Admin can perform this action",
        )
    return user


def client_ip(request: Request) -> str | None:
    # X-Forwarded-For first hop wins behind a reverse proxy.
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def session_id(request: Request) -> str | None:
    return request.headers.get("X-Session-Id")
