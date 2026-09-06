from starlette.requests import Request

from app.adapters.protocols import Identity
from app.core.auth import SESSION_COOKIE_NAME, decode_token
from app.core.config import get_settings


def _identity_from(email: str) -> Identity:
    return Identity(
        email=email,
        display_name=email.split("@")[0].replace(".", " ").title(),
        groups=[],
    )


class JWTSSOAdapter:
    """Identity from the app's own signed JWT.

    The token reaches us two ways, and both resolve here so password login and
    SSO share one code path:

      1. The `genaiforge_session` httpOnly cookie — how browsers authenticate. Set
         server-side by the login endpoint; invisible
         to JavaScript, so an injected script has no token to steal.
      2. `Authorization: Bearer <jwt>` — the documented fallback for non-browser
         clients (curl, Postman, service-to-service).

    Cookie first: when a browser somehow carries both, the httpOnly one is the
    trustworthy one.

    Escape hatch: when settings.auth_dev_mode is True we also honor the legacy
    `X-Dev-User: <email>` header (no password) for local testing. This is OFF by
    default, so real login is mandatory in every deployed environment.
    """

    async def get_identity(self, request: Request) -> Identity | None:
        cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
        if cookie_token:
            email = decode_token(cookie_token)
            if email:
                return _identity_from(email)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            email = decode_token(auth[7:])
            if email:
                return _identity_from(email)

        if get_settings().auth_dev_mode:
            dev_user = request.headers.get("X-Dev-User")
            if dev_user:
                return _identity_from(dev_user)

        return None
