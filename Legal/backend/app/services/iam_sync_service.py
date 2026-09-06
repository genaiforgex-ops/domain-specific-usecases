"""Sync LegalOS users from the Central IAM platform."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Role
from app.core.security import hash_password
from app.models.user import User
from app.services.iam_service import IamService, IamServiceError, IamUserRole

logger = logging.getLogger(__name__)

# Highest-privilege role wins when IAM returns multiple roles.
_ROLE_PRIORITY: tuple[Role, ...] = (
    Role.SUPER_ADMIN,
    Role.LEGAL_ADMIN,
    Role.LEGAL_USER,
    Role.BUSINESS_USER,
    Role.READ_ONLY,
)


@dataclass
class IamSyncResult:
    created: int = 0
    updated: int = 0
    deactivated: int = 0
    unchanged: int = 0

    @property
    def total_changes(self) -> int:
        return self.created + self.updated + self.deactivated


def _pick_role(roles: list[str]) -> str:
    """Map IAM role strings to the highest-priority LegalOS role."""
    normalized = {r.strip().lower() for r in roles if r.strip()}
    for role in _ROLE_PRIORITY:
        if role.value in normalized:
            return role.value
    logger.warning("Unknown IAM roles %s — defaulting to legal_user", roles)
    return Role.LEGAL_USER.value


def _display_name(email: str) -> str:
    local = email.split("@", 1)[0]
    return local.replace(".", " ").replace("_", " ").title()


def _apply_iam_user(db: Session, iam_user: IamUserRole, *, now: datetime) -> str:
    """Upsert one IAM user. Returns 'created', 'updated', or 'unchanged'."""
    email = iam_user.email.lower()
    role = _pick_role(iam_user.roles)
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if existing is None:
        db.add(
            User(
                email=email,
                full_name=_display_name(email),
                hashed_password=hash_password("LegalOS@2026"),
                role=role,
                is_active=True,
                iam_managed=True,
                iam_synced_at=now,
            )
        )
        return "created"

    changed = False
    if existing.role != role:
        existing.role = role
        changed = True
    if not existing.is_active:
        existing.is_active = True
        changed = True
    if not existing.iam_managed:
        existing.iam_managed = True
        changed = True
    if existing.iam_synced_at != now:
        existing.iam_synced_at = now
        changed = True
    return "updated" if changed else "unchanged"


async def sync_all_users_from_iam(db: Session, *, iam: IamService | None = None) -> IamSyncResult:
    """Pull the full user roster from IAM and reconcile the local DB."""
    service = iam or IamService()
    if not service.configured:
        logger.info("IAM sync skipped — client secret not configured")
        return IamSyncResult()

    try:
        iam_users = await service.resolve_all_users()
    except IamServiceError:
        logger.exception("IAM full sync failed")
        raise

    now = datetime.now(timezone.utc)
    result = IamSyncResult()
    iam_emails = {u.email.lower() for u in iam_users}

    for iam_user in iam_users:
        outcome = _apply_iam_user(db, iam_user, now=now)
        if outcome == "created":
            result.created += 1
        elif outcome == "updated":
            result.updated += 1
        else:
            result.unchanged += 1

    # Deactivate IAM-managed users removed from the central platform.
    local_iam_users = db.execute(select(User).where(User.iam_managed.is_(True))).scalars().all()
    for user in local_iam_users:
        if user.email.lower() not in iam_emails and user.is_active:
            user.is_active = False
            user.iam_synced_at = now
            result.deactivated += 1

    db.flush()
    logger.info(
        "IAM sync complete: created=%d updated=%d deactivated=%d unchanged=%d",
        result.created,
        result.updated,
        result.deactivated,
        result.unchanged,
    )
    return result


async def sync_user_from_iam(db: Session, email: str, *, iam: IamService | None = None) -> User | None:
    """Resolve and upsert a single user from IAM. Deactivates if removed centrally."""
    service = iam or IamService()
    if not service.configured:
        return db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()

    normalized = email.strip().lower()
    now = datetime.now(timezone.utc)

    try:
        iam_user = await service.resolve_user(normalized)
    except IamServiceError:
        logger.exception("IAM single-user sync failed for %s", normalized)
        raise

    if iam_user is None:
        existing = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
        if existing and existing.iam_managed and existing.is_active:
            existing.is_active = False
            existing.iam_synced_at = now
            db.flush()
        return existing

    outcome = _apply_iam_user(db, iam_user, now=now)
    db.flush()
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if outcome != "unchanged":
        logger.info("IAM sync for %s: %s", normalized, outcome)
    return user


def sync_all_users_from_iam_sync(db: Session, *, iam: IamService | None = None) -> IamSyncResult:
    """Blocking wrapper for startup / sync endpoints."""
    return asyncio.run(sync_all_users_from_iam(db, iam=iam))
