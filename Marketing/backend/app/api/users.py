"""User directory — active role accounts for the signed-in app."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


def annotate_roles(users: list[User]) -> list[User]:
    """Attach each account's roles from the local ``User.role`` column."""
    for u in users:
        u.roles = [u.role] if u.role else []
    return users


@router.get("", response_model=list[UserOut])
def list_users(
    _current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[User]:
    users = list(
        db.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name)
        ).scalars()
    )
    return annotate_roles(users)
