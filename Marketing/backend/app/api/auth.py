"""Auth routes — email + password login.

Sign-in verifies a local password hash, then mints an app JWT into an httpOnly
session cookie. Roles travel inside that signed token (from the user row).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.security import create_access_token, verify_password
from app.core.session import clear_session_cookie, set_session_cookie
from app.database import get_db
from app.models.user import User
from app.schemas.auth import AuthConfig, LoginRequest, SwitchRoleRequest, TokenResponse, UserOut
from app.services import auth_service

logger = logging.getLogger("app.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User, roles: list[str], active_role: str) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=active_role,
        is_active=user.is_active,
        roles=roles,
        active_role=active_role,
    )


def _issue_session(response: Response, user: User, roles: list[str], active_role: str) -> str:
    token = create_access_token(str(user.id), roles=roles, active_role=active_role)
    set_session_cookie(response, token)
    return token


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = auth_service.get_active_user_by_email(db, body.email)
    if user is None or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    roles = auth_service.roles_for_user(user)
    active_role = auth_service.choose_active_role(roles, preferred=user.role)
    if user.role != active_role:
        user.role = active_role
        db.commit()

    token = _issue_session(response, user, roles, active_role)
    return TokenResponse(access_token=token, user=_user_out(user, roles, active_role))


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> UserOut:
    roles = getattr(current, "session_roles", None) or [current.role]
    active = getattr(current, "active_role", None) or current.role
    return _user_out(current, roles, active)


@router.post("/switch-role", response_model=UserOut)
def switch_role(
    body: SwitchRoleRequest,
    response: Response,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    granted = getattr(current, "session_roles", None) or [current.role]
    if body.role not in granted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not granted")
    current.role = body.role
    db.commit()
    _issue_session(response, current, granted, body.role)
    return _user_out(current, granted, body.role)


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    s = get_settings()
    return AuthConfig(environment=s.environment, password_login=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    clear_session_cookie(response)
