"""Session cookie helpers.

The session is an httpOnly cookie holding the app's own JWT. Cookie names are
app-specific because cookies are scoped by (domain, path, name) and NOT by port.
"""

from fastapi import Response

from app.config import settings

SESSION_COOKIE_NAME = "gf_session"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        samesite="lax",
        secure=not settings.is_local_dev,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
