"""Email + password authentication. No SSO / Identity Provider."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import AuditService
from app.core.auth import (
    clear_session_cookie,
    create_access_token,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AuthConfigResponse,
    ChangePasswordRequest,
    DevLoginRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=[r.role for r in user.roles],
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
    )


async def _load_user(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.email == email.strip().lower())
    )
    return result.scalar_one_or_none()


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    settings = get_settings()
    return AuthConfigResponse(
        environment=settings.environment,
        sso_enabled=False,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return _user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    audit = AuditService(db)
    user = await _load_user(db, body.email)

    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        await audit.log(
            event_type="login_failed",
            entity_type="auth",
            entity_id=body.email,
            payload={"email": body.email},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user.last_login = datetime.now(timezone.utc)
    await audit.log(
        event_type="login",
        entity_type="auth",
        entity_id=str(user.id),
        actor_id=user.id,
        payload={"email": user.email},
    )
    token = create_access_token(user.email)
    set_session_cookie(response, token)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/change-password", response_model=UserResponse)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await AuditService(db).log(
        event_type="user.password_changed",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
    )
    return _user_response(user)


@router.post("/dev-login", response_model=UserResponse)
async def dev_login(body: DevLoginRequest, db: AsyncSession = Depends(get_db)):
    if not get_settings().auth_dev_mode:
        raise HTTPException(status_code=404, detail="Not found")
    user = await _load_user(db, body.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Run seed script.")
    return _user_response(user)


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookie(response)
    return {"message": "Logged out successfully"}
