"""MSA tracker access — owner (legal) vs shared view/edit."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rbac import Permission, Role, has_permission
from app.database import get_db
from app.models.msa import MSATracker
from app.models.msa_share import MSAShare
from app.models.user import User

ACCESS_OWNER = "owner"
ACCESS_VIEW = "view"
ACCESS_EDIT = "edit"


def _role(user: User) -> Role:
    try:
        return Role(user.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unknown role") from exc


def is_msa_owner(user: User) -> bool:
    return has_permission(_role(user), Permission.MSA_AUTOMATION)


def can_use_msa_module(user: User) -> bool:
    role = _role(user)
    return has_permission(role, Permission.MSA_AUTOMATION) or has_permission(
        role, Permission.MSA_SHARED_VIEW
    )


def get_share(db: Session, tracker_id: int, user_id: int) -> MSAShare | None:
    return db.execute(
        select(MSAShare).where(MSAShare.tracker_id == tracker_id, MSAShare.user_id == user_id)
    ).scalar_one_or_none()


def access_level_for(user: User, tracker_id: int, db: Session) -> str | None:
    if is_msa_owner(user):
        return ACCESS_OWNER
    share = get_share(db, tracker_id, user.id)
    if share is None:
        return None
    if not has_permission(_role(user), Permission.MSA_SHARED_VIEW):
        return None
    return ACCESS_EDIT if share.access_level == ACCESS_EDIT else ACCESS_VIEW


def require_msa_module(user: User = Depends(get_current_user)) -> User:
    if not can_use_msa_module(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role lacks permission for MSA module",
        )
    return user


def require_msa_owner(user: User = Depends(get_current_user)) -> User:
    if not is_msa_owner(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MSA automation permission required",
        )
    return user


def load_tracker_with_access(
    tracker_id: int,
    user: User,
    db: Session,
    *,
    min_level: str = ACCESS_VIEW,
) -> tuple[MSATracker, str]:
    tracker = db.get(MSATracker, tracker_id)
    if tracker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found")
    level = access_level_for(user, tracker_id, db)
    if level is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found")
    if min_level == ACCESS_EDIT and level not in (ACCESS_OWNER, ACCESS_EDIT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit access required")
    if min_level == ACCESS_OWNER and level != ACCESS_OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return tracker, level


def can_apply_msa_changes(user: User, level: str) -> bool:
    if level == ACCESS_OWNER:
        return has_permission(_role(user), Permission.APPROVE_AI_OUTPUT)
    if level == ACCESS_EDIT:
        return True
    return False


def tracker_access_dependency(min_level: str = ACCESS_VIEW):
    def dependency(
        tracker_id: int,
        user: User = Depends(require_msa_module),
        db: Session = Depends(get_db),
    ) -> tuple[MSATracker, str, User]:
        tracker, level = load_tracker_with_access(tracker_id, user, db, min_level=min_level)
        return tracker, level, user

    return dependency
