import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    SESSION_COOKIE_NAME,
    client_ip,
    clear_session_cookie,
    get_current_user,
    session_id,
    set_session_cookie,
)
from app.config import settings
from app.core.rbac import ROLE_PERMISSIONS, Role
from app.core.security import (
    MSG_ABSOLUTE_EXPIRED,
    create_access_token,
    decode_access_token,
    hash_password,
    session_started_at_from_claims,
    token_expires_in_seconds,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import KeycloakCallbackRequest, LoginRequest, TokenResponse, ExchangeSSOCodeBody
from app.schemas.user import AcceptInviteRequest, InviteTokenInfo, UserOut
from app.services.audit_service import write_audit
from app.services.iam_sync_service import sync_user_from_iam


router = APIRouter(prefix="/api/auth", tags=["auth"])

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _require_keycloak_sso() -> None:
    """FastAPI dependency: raises 404 when Keycloak SSO is not active.

    SSO is active only when LEGALOS_ENV is in _KEYCLOAK_SSO_ENVS (currently: dev, uat).
    To enable SSO in another environment, add it to _KEYCLOAK_SSO_ENVS in config.py.
    """
    if not settings.keycloak_sso_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.get("/config")
def get_config() -> dict:
    """
    Public endpoint for configuration needed before authentication.
    sso_enabled is derived from the same check that actually gates the SSO
    endpoints (_require_keycloak_sso) — adding an env to _KEYCLOAK_SSO_ENVS
    is the only change needed to also flip this for the frontend, no
    separate build-time flag to keep in sync.
    """
    return {"sso_enabled": settings.keycloak_sso_enabled}


def _token_response(token: str, payload: dict | None = None) -> TokenResponse:
    return TokenResponse(
        access_token=token,
        expires_in=token_expires_in_seconds(payload),
        idle_timeout_seconds=settings.access_token_expire_minutes * 60,
        absolute_timeout_seconds=settings.access_token_absolute_hours * 3600,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = payload.email.lower()
    if settings.iam_sync_enabled:
        user = await sync_user_from_iam(db, email)
        db.commit()
    else:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        # Audit failed attempts to surface brute-force.
        write_audit(
            db,
            user=None,
            action_type="login_failed",
            module="auth",
            input_summary=f"email={email}",
            ip_address=client_ip(request),
            session_id=session_id(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    user.last_login_at = datetime.now(timezone.utc)
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role})
    write_audit(
        db,
        user=user,
        action_type="login",
        module="auth",
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    set_session_cookie(response, token)
    return _token_response(token)


@router.post("/logout")
def logout(response: Response):
    """Clear the session cookie server-side — JS can't touch an httpOnly
    cookie directly, so this round-trip is required."""
    clear_session_cookie(response)
    return {"message": "Logged out successfully"}


@router.post("/keycloak/callback", response_model=TokenResponse)
async def keycloak_callback_post(
    payload: KeycloakCallbackRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(_require_keycloak_sso),
) -> TokenResponse:
    """Exchange Keycloak authorization code for legalOS user session token (POST)."""
    token_res = await _process_keycloak_exchange(
        code=payload.code,
        redirect_uri=payload.redirect_uri,
        request=request,
        db=db,
    )
    set_session_cookie(response, token_res.access_token)
    return token_res


@router.get("/keycloak", summary="Redirect to Keycloak SSO login screen")
def keycloak_login(
    request: Request,
    state: str | None = None,
    _: None = Depends(_require_keycloak_sso),
):
    """Initiate Keycloak OpenID Connect authentication flow."""
    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/api/auth/keycloak/callback"

    keycloak_auth_url = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/auth"
    params = {
        "client_id": settings.keycloak_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "kc_idp_hint": settings.keycloak_idp_hint,
    }
    if state:
        params["state"] = state
    query_str = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{keycloak_auth_url}?{query_str}")


@router.get("/keycloak/callback", summary="Keycloak SSO callback handler (GET)")
async def keycloak_callback_get(
    request: Request,
    code: str,
    state: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(_require_keycloak_sso),
):
    """GET callback when Keycloak redirects directly to backend."""
    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/api/auth/keycloak/callback"
    frontend_url = settings.frontend_base_url.rstrip('/') if settings.frontend_base_url else "http://localhost:5176"
    try:
        token_res = await _process_keycloak_exchange(code=code, redirect_uri=redirect_uri, request=request, db=db)
        # Set the cookie directly on the redirect — no token in the URL at
        # all now, closing off the "tokens end up in access/proxy logs"
        # weakness that a query-string handoff otherwise carries.
        redirect = RedirectResponse(f"{frontend_url}/")
        set_session_cookie(redirect, token_res.access_token)
        return redirect
    except HTTPException as exc:
        return RedirectResponse(f"{frontend_url}/login?error={exc.detail}")
    except Exception as exc:
        logger.exception("Keycloak SSO GET callback error: %s", exc)
        return RedirectResponse(f"{frontend_url}/login?error=sso_failed")


@router.post("/exchange-sso-code", response_model=TokenResponse)
async def exchange_sso_code_endpoint(
    body: ExchangeSSOCodeBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(_require_keycloak_sso),
) -> TokenResponse:
    """
    Exchanges a single-use authorization code from Central IAM (server-to-server)
    for verified user credentials, auto-provisions the user, and returns TokenResponse.
    """
    import httpx

    iam_backend = settings.iam_backend_url.rstrip("/")
    exchange_url = f"{iam_backend}/auth/sso/exchange-code"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(exchange_url, json={"code": body.code})

        if res.status_code != 200:
            error_detail = "Failed to exchange SSO code"
            try:
                error_detail = res.json().get("detail", error_detail)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail,
            )

        iam_user = res.json()
        email = iam_user.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No email returned from Central IAM.",
            )

        email = str(email).lower()
        full_name = iam_user.get("full_name") or email.split("@")[0]

        # Sync role from Central IAM (source of truth).
        user = await sync_user_from_iam(db, email)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not registered for LegalOS in Central IAM.",
            )

        if iam_user.get("full_name"):
            full_name = iam_user.get("full_name")
            if user.full_name != full_name:
                user.full_name = full_name

        user.last_login_at = datetime.now(timezone.utc)
        db.commit()

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account disabled",
            )

        # Create access token and write audit log
        token = create_access_token(subject=str(user.id), extra_claims={"role": user.role})
        write_audit(
            db,
            user=user,
            action_type="login_sso",
            module="auth",
            ip_address=client_ip(request),
            session_id=session_id(request),
        )
        db.commit()

        set_session_cookie(response, token)
        return _token_response(token)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Central IAM SSO code exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SSO Exchange Error: {type(exc).__name__}: {str(exc)}",
        )


async def _process_keycloak_exchange(
    code: str,
    redirect_uri: str,
    request: Request,
    db: Session,
) -> TokenResponse:
    import httpx
    from jose import jwt as jose_jwt

    token_url = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.keycloak_client_id,
        "redirect_uri": redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(token_url, data=data)
            if resp.status_code != 200:
                logger.error("Keycloak token exchange failed (%s): %s", resp.status_code, resp.text)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Keycloak token exchange failed: {resp.text}",
                )

            tokens = resp.json()
            id_token = tokens.get("id_token") or tokens.get("access_token")
            claims = {}
            if isinstance(id_token, str) and "." in id_token:
                try:
                    claims = jose_jwt.decode(
                        id_token,
                        "",
                        options={
                            "verify_signature": False,
                            "verify_aud": False,
                            "verify_exp": False,
                            "verify_at_hash": False,
                        },
                    )
                except Exception:
                    import base64, json
                    parts = id_token.split(".")
                    if len(parts) >= 2:
                        padded = parts[1] + "=" * (-len(parts[1]) % 4)
                        claims = json.loads(base64.urlsafe_b64decode(padded))

            email = claims.get("email") or claims.get("preferred_username") or claims.get("sub")
            full_name = claims.get("name") or claims.get("given_name") or email

            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email not found in Keycloak token claims",
                )

            email = str(email).lower()

            user = await sync_user_from_iam(db, email)
            if user is None:
                users_list = db.execute(select(User)).scalars().all()
                user = User(
                    email=email,
                    full_name=full_name,
                    role="super_admin" if len(users_list) == 0 else "legal_user",
                    is_active=True,
                    hashed_password=hash_password("LegalOS@2026"),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                if full_name and user.full_name != full_name:
                    user.full_name = full_name
                user.last_login_at = datetime.now(timezone.utc)
                db.commit()

            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

            token = create_access_token(subject=str(user.id), extra_claims={"role": user.role})
            write_audit(
                db,
                user=user,
                action_type="login_sso",
                module="auth",
                ip_address=client_ip(request),
                session_id=session_id(request),
            )
            db.commit()
            return _token_response(token)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Keycloak SSO callback exception: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SSO Error: {type(exc).__name__}: {str(exc)}",
        )


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    request: Request,
    response: Response,
    token: str | None = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Slide the idle window forward while the user is active.

    Requires a still-valid access token. Preserves ``auth_time`` so the absolute
    session cap from login cannot be extended indefinitely.
    """
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        token = cookie_token
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if payload.get("purpose") in ("invite", "file_download"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This token cannot be refreshed",
        )

    started = session_started_at_from_claims(payload)
    absolute_end = started + timedelta(hours=settings.access_token_absolute_hours)
    now = datetime.now(timezone.utc)
    if now >= absolute_end:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MSG_ABSOLUTE_EXPIRED)

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user"
        )

    new_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role},
        session_started_at=started,
    )
    # Decode without re-checking absolute (just minted) for accurate expires_in.
    from jose import jwt as jose_jwt

    new_payload = jose_jwt.get_unverified_claims(new_token)
    set_session_cookie(response, new_token)
    return _token_response(new_token, new_payload)


def _decode_invite(token: str, db: Session) -> User:
    """Decode an invite token, enforce purpose, and return the target user.
    Raises HTTPException with a user-facing message on any problem."""
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite link is invalid or has expired — ask an admin to resend it.",
        ) from exc
    if payload.get("purpose") != "invite":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This is not a valid invite link."
        )
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or user.email != payload.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This invite is no longer valid."
        )
    return user


@router.get("/invite/validate", response_model=InviteTokenInfo)
def validate_invite(token: str, db: Session = Depends(get_db)) -> InviteTokenInfo:
    try:
        user = _decode_invite(token, db)
    except HTTPException as exc:
        return InviteTokenInfo(valid=False, detail=str(exc.detail))
    if user.is_active:
        return InviteTokenInfo(
            valid=False, detail="Account already activated — please sign in.", email=user.email
        )
    return InviteTokenInfo(valid=True, email=user.email, full_name=user.full_name)


@router.post("/accept-invite", response_model=TokenResponse)
def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = _decode_invite(payload.token, db)
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account already activated — please sign in.",
        )
    user.hashed_password = hash_password(payload.password)
    user.is_active = True
    user.last_login_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user=user,
        action_type="user_activated",
        module="auth",
        input_summary=f"email={user.email}",
        target_id=user.id,
        ip_address=client_ip(request),
        session_id=session_id(request),
    )
    db.commit()
    # Log them straight in on success.
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role})
    set_session_cookie(response, token)
    return _token_response(token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    perms: list[str] = []
    try:
        perms = sorted(p.value for p in ROLE_PERMISSIONS.get(Role(user.role), set()))
    except ValueError:
        perms = []
    return UserOut.model_validate({**user.__dict__, "permissions": perms})
