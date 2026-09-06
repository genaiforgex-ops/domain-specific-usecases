"""Admin user-management routes — create accounts, assign roles, reset
passwords, and enable/disable accounts. Admin (AD) only.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.api.users import annotate_roles
from app.database import get_db
from app.models.user import User
from app.schemas.user import AdminUserOut, PasswordReset, UserCreate, UserUpdate
from app.services import email_service, user_service

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _load(db: Session, user_id: uuid.UUID) -> User:
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _guard_admin_lockout(
    db: Session,
    admin: User,
    user: User,
    *,
    new_is_active: bool | None,
) -> None:
    losing_admin = user_service.is_admin(user) and new_is_active is False
    if not losing_admin:
        return
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't disable your own admin account",
        )
    if user_service.active_admin_count(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one active admin is required",
        )


@router.get("", response_model=list[AdminUserOut])
def list_users(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    return annotate_roles(user_service.list_users(db))


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> User:
    if user_service.email_taken(db, str(body.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    user = user_service.create_user(db, body)
    email_service.notify_user_invited(user, admin)
    return annotate_roles([user])[0]


@router.patch("/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> User:
    user = _load(db, user_id)

    if body.email is not None and user_service.email_taken(db, str(body.email), exclude_id=user.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    _guard_admin_lockout(db, admin, user, new_is_active=body.is_active)

    return annotate_roles([user_service.apply_update(db, user, body)])[0]


@router.delete("/{user_id}", response_model=AdminUserOut)
def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> User:
    user = _load(db, user_id)
    _guard_admin_lockout(db, admin, user, new_is_active=False)
    return annotate_roles([user_service.apply_update(db, user, UserUpdate(is_active=False))])[0]


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID,
    body: PasswordReset,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> None:
    user = _load(db, user_id)
    user_service.set_password(db, user, body.password)
