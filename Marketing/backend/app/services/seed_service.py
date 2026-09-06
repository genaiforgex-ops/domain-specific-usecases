"""Startup account seeding — five role demo accounts for local / Docker demos."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.models.role_default import RoleDefault
from app.models.user import User
from app.services.assignment_service import ASSIGNABLE_ROLES

# Email / role / display name for the showcase accounts. Shared password comes
# from SEED_PASSWORD in .env.
SEED_ACCOUNTS: tuple[tuple[str, str, str], ...] = (
    ("cw@genaiforge.in", "CW", "Priya Nair"),
    ("ml@genaiforge.in", "ML", "Rohan Kapoor"),
    ("pl@genaiforge.in", "PL", "Sana Iqbal"),
    ("ds@genaiforge.in", "DS", "Karthik Reddy"),
    ("admin@genaiforge.in", "AD", "Meera Krishnan"),
)


def seed_users(db: Session) -> int:
    """Create any missing seed accounts and wire default assignees."""
    created = 0
    password = settings.seed_password
    by_role: dict[str, User] = {}
    for email, role, full_name in SEED_ACCOUNTS:
        handle = email.strip().lower()
        existing = db.execute(
            select(User).where(func.lower(User.email) == handle)
        ).scalars().first()
        if existing is not None:
            by_role[role] = existing
            continue
        user = User(
            email=handle,
            full_name=full_name,
            role=role,
            hashed_password=hash_password(password),
            is_active=True,
        )
        db.add(user)
        by_role[role] = user
        created += 1
    if created:
        db.flush()

    for role in ASSIGNABLE_ROLES:
        user = by_role.get(role)
        if user is None:
            continue
        rd = db.get(RoleDefault, role)
        if rd is None:
            db.add(RoleDefault(role=role, user_id=user.id))
        elif rd.user_id is None:
            rd.user_id = user.id

    db.commit()
    return created
