import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import AuditService
from app.core.auth import hash_password
from app.core.database import get_db
from app.core.security import Role, require_permission
from app.models.config import ModuleAIConfig
from app.models.user import User, UserRole
from app.models.vendor import DDWeightConfig
from app.schemas.auth import (
    ResetPasswordRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.common import AIConfigResponse, AIConfigUpdate
from app.schemas.vendor import DDWeightUpdate

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ROLES = {r.value for r in Role}


def _user_response(u: User) -> UserResponse:
    return UserResponse(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        roles=[r.role for r in u.roles],
        is_active=u.is_active,
        last_login=u.last_login,
        created_at=u.created_at,
    )


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    return u


async def _active_admin_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(func.distinct(User.id)))
        .select_from(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(User.is_active.is_(True), UserRole.role == Role.ADMIN.value)
    )
    return result.scalar() or 0


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:users")),
):
    result = await db.execute(
        select(User).options(selectinload(User.roles)).order_by(User.created_at)
    )
    return [_user_response(u) for u in result.scalars().all()]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:users")),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Allowed: {sorted(VALID_ROLES)}")
    email = body.email.strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "A user with this email already exists")

    new_user = User(
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()
    db.add(UserRole(user_id=new_user.id, role=body.role))
    await db.flush()
    await db.refresh(new_user, ["roles"])
    await AuditService(db).log(
        event_type="user.created",
        entity_type="user",
        entity_id=str(new_user.id),
        actor_id=user.id,
        payload={"email": email, "role": body.role},
    )
    return _user_response(new_user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:users")),
):
    target = await _get_user(db, user_id)

    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Allowed: {sorted(VALID_ROLES)}")

    # Guard: don't let the last active admin lose admin or be deactivated.
    demoting_admin = (
        body.role is not None
        and body.role != Role.ADMIN.value
        and any(r.role == Role.ADMIN.value for r in target.roles)
    )
    deactivating = body.is_active is False and target.is_active
    if (demoting_admin or deactivating) and await _active_admin_count(db) <= 1 and any(
        r.role == Role.ADMIN.value for r in target.roles
    ):
        raise HTTPException(400, "Cannot remove the last active admin")

    if body.display_name is not None:
        target.display_name = body.display_name.strip()
    if body.is_active is not None:
        target.is_active = body.is_active
    if body.role is not None:
        for r in list(target.roles):
            await db.delete(r)
        await db.flush()
        db.add(UserRole(user_id=target.id, role=body.role))
        await db.flush()
        await db.refresh(target, ["roles"])

    await AuditService(db).log(
        event_type="user.updated",
        entity_type="user",
        entity_id=str(target.id),
        actor_id=user.id,
        payload={"display_name": body.display_name, "is_active": body.is_active, "role": body.role},
    )
    return _user_response(target)


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
async def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:users")),
):
    target = await _get_user(db, user_id)
    target.password_hash = hash_password(body.new_password)
    await AuditService(db).log(
        event_type="user.password_reset",
        entity_type="user",
        entity_id=str(target.id),
        actor_id=user.id,
    )
    return _user_response(target)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:users")),
):
    # Soft delete: deactivate rather than hard-delete so this user's audit and
    # usage rows keep a valid actor reference.
    target = await _get_user(db, user_id)
    if (
        any(r.role == Role.ADMIN.value for r in target.roles)
        and target.is_active
        and await _active_admin_count(db) <= 1
    ):
        raise HTTPException(400, "Cannot deactivate the last active admin")
    target.is_active = False
    await AuditService(db).log(
        event_type="user.deactivated",
        entity_type="user",
        entity_id=str(target.id),
        actor_id=user.id,
    )
    return _user_response(target)


@router.get("/ai-config", response_model=list[AIConfigResponse])
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_config")),
):
    result = await db.execute(select(ModuleAIConfig))
    return result.scalars().all()


@router.patch("/ai-config/{module}", response_model=AIConfigResponse)
async def update_ai_config(
    module: str,
    body: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:ai_config")),
):
    result = await db.execute(select(ModuleAIConfig).where(ModuleAIConfig.module == module))
    config = result.scalar_one_or_none()
    if not config:
        config = ModuleAIConfig(module=module)
        db.add(config)
    if body.kill_switch is not None:
        config.kill_switch = body.kill_switch
    if body.confidence_threshold is not None:
        config.confidence_threshold = body.confidence_threshold
    await db.flush()
    return config


@router.get("/dd-weights")
async def get_dd_weights(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:dd_weights")),
):
    result = await db.execute(select(DDWeightConfig).where(DDWeightConfig.is_active.is_(True)))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "No active config")
    return {"version": config.version, "category_weights": json.loads(config.category_weights)}


@router.put("/dd-weights")
async def update_dd_weights(
    body: DDWeightUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:dd_weights")),
):
    result = await db.execute(select(DDWeightConfig).where(DDWeightConfig.is_active.is_(True)))
    for old in result.scalars().all():
        old.is_active = False
    new_version = f"v{len(body.category_weights)}"
    config = DDWeightConfig(
        version=new_version,
        category_weights=json.dumps(body.category_weights),
        is_active=True,
    )
    db.add(config)
    await db.flush()
    return {"version": config.version, "category_weights": body.category_weights}
