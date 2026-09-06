from enum import Enum

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"


ALL_PERMISSIONS: set[str] = {
    "m1:read", "m1:create", "m1:review", "m1:approve", "m1:override", "m1:clause_edit", "m1:agent_manage",
    "m2:read", "m2:create", "m2:review", "m2:approve",
    "m3:read", "m3:create", "m3:review", "m3:approve", "m3:override",
    "forms:read", "forms:fill", "forms:submit", "forms:manage", "forms:assign",
    "admin:users", "admin:ai_config", "admin:clauses", "admin:dd_weights", "admin:sources",
    "audit:read", "audit:export", "search:read", "notifications:read", "metrics:read",
}

USER_PERMISSIONS: set[str] = {
    "forms:read", "forms:fill", "forms:submit", "notifications:read", "m1:read",
}

ADMIN_ONLY_PERMISSIONS: set[str] = {
    "admin:users", "admin:ai_config", "admin:clauses", "admin:dd_weights", "admin:sources",
    "audit:read", "audit:export", "metrics:read",
}


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: ALL_PERMISSIONS,
    Role.USER: USER_PERMISSIONS,
}


def _permissions_for_roles(roles: list[str]) -> set[str]:
    perms: set[str] = set()
    for role_name in roles:
        try:
            role = Role(role_name)
            perms |= ROLE_PERMISSIONS.get(role, set())
        except ValueError:
            continue
    return perms


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    from app.adapters.factory import get_sso_adapter

    sso = get_sso_adapter()
    identity = await sso.get_identity(request)
    if not identity:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.email == identity.email)
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_permission(permission: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        role_names = [r.role for r in user.roles]
        perms = _permissions_for_roles(role_names)
        if permission not in perms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return user

    return checker
