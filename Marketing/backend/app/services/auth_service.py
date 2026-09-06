"""Authentication business logic — email identity and local password accounts."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger("app.auth")


def get_active_user_by_email(db: Session, email: str) -> User | None:
    """The single active account for ``email``."""
    handle = email.strip().lower()
    rows = list(
        db.execute(select(User).where(func.lower(User.email) == handle, User.is_active.is_(True)))
        .scalars()
    )
    if len(rows) != 1:
        if len(rows) > 1:
            logger.warning("Ambiguous email %s matches %d active accounts", handle, len(rows))
        return None
    return rows[0]


def roles_for_user(user: User) -> list[str]:
    """Roles this account may act as. Local accounts hold a single primary role."""
    return [user.role] if user.role else []


def choose_active_role(granted: list[str], preferred: str | None = None) -> str:
    if preferred and preferred in granted:
        return preferred
    return granted[0]
