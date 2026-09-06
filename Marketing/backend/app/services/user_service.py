"""User-management business logic — the admin-only directory CRUD."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import ROLES, User
from app.schemas.user import UserCreate, UserUpdate

ADMIN_ROLE = "AD"


def list_users(db: Session) -> list[User]:
    return list(
        db.execute(select(User).order_by(User.role, User.full_name)).scalars()
    )


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def email_taken(db: Session, email: str, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return db.execute(stmt).scalar_one_or_none() is not None


def is_admin(user: User) -> bool:
    return user.role == ADMIN_ROLE


def active_admin_count(db: Session) -> int:
    return db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == ADMIN_ROLE, User.is_active.is_(True))
    ).scalar_one()


def create_user(db: Session, data: UserCreate) -> User:
    role = data.role.strip().upper() if data.role else "CW"
    if role not in ROLES:
        role = "CW"
    password = data.password or None
    user = User(
        email=str(data.email).strip().lower(),
        full_name=data.full_name.strip(),
        role=role,
        hashed_password=hash_password(password) if password else None,
        is_active=data.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def apply_update(db: Session, user: User, data: UserUpdate) -> User:
    if data.email is not None:
        user.email = str(data.email).strip().lower()
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.role is not None:
        role = data.role.strip().upper()
        if role in ROLES:
            user.role = role
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, password: str) -> None:
    user.hashed_password = hash_password(password)
    db.commit()
