"""Default-assignee routing.

New work auto-routes to a single admin-configured account per role.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role_default import RoleDefault
from app.models.user import User

ASSIGNABLE_ROLES = ("CW", "ML", "DS")

ROLE_LABELS = {
    "CW": "Copywriter",
    "ML": "Marketing Lead",
    "PL": "Product Lead",
    "DS": "Designer",
}


def holds_role(user: User, role: str) -> bool:
    return user.role == role


class DefaultAssigneeError(Exception):
    """No usable default is configured for a role that work is routing to."""


def list_defaults(db: Session) -> dict[str, User | None]:
    rows = {
        rd.role: rd.user
        for rd in db.execute(select(RoleDefault)).scalars()
        if rd.role in ASSIGNABLE_ROLES
    }
    return {role: rows.get(role) for role in ASSIGNABLE_ROLES}


def set_default(db: Session, role: str, user: User) -> RoleDefault:
    if role not in ASSIGNABLE_ROLES:
        raise DefaultAssigneeError(f"{role!r} is not an assignable role")
    if not user.is_active:
        raise DefaultAssigneeError(f"{user.full_name} is not an active account")
    if not holds_role(user, role):
        raise DefaultAssigneeError(
            f"{user.full_name} does not hold the {ROLE_LABELS.get(role, role)} role"
        )

    rd = db.get(RoleDefault, role)
    if rd is None:
        rd = RoleDefault(role=role, user_id=user.id)
        db.add(rd)
    else:
        rd.user_id = user.id
    return rd


def require_default(db: Session, role: str) -> User:
    rd = db.get(RoleDefault, role)
    label = ROLE_LABELS.get(role, role)
    if rd is None:
        raise DefaultAssigneeError(
            f"No default {label} is configured — ask an Admin to set one."
        )
    user = db.get(User, rd.user_id)
    if user is None or not user.is_active or not holds_role(user, role):
        raise DefaultAssigneeError(
            f"The default {label} is no longer available — ask an Admin to update it."
        )
    return user
