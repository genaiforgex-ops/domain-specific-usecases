"""Unit tests for Central IAM user sync."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.rbac import Role
from app.core.security import hash_password
from app.database import Base
from app.models.user import User
from app.services.iam_service import IamUserRole
from app.services.iam_sync_service import (
    _pick_role,
    sync_all_users_from_iam,
    sync_user_from_iam,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_pick_role_uses_highest_privilege() -> None:
    assert _pick_role(["legal_user", "super_admin"]) == Role.SUPER_ADMIN.value
    assert _pick_role(["unknown_role"]) == Role.LEGAL_USER.value


@pytest.mark.asyncio
async def test_sync_all_creates_updates_and_deactivates(db: Session) -> None:
    stale = User(
        email="removed@jiofinance.in",
        full_name="Removed User",
        hashed_password=hash_password("x"),
        role=Role.LEGAL_USER.value,
        is_active=True,
        iam_managed=True,
        iam_synced_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    existing = User(
        email="vikas.maurya@jiofinance.in",
        full_name="Old Name",
        hashed_password=hash_password("x"),
        role=Role.LEGAL_USER.value,
        is_active=True,
        iam_managed=False,
    )
    db.add_all([stale, existing])
    db.commit()

    iam_users = [
        IamUserRole(email="vikas.maurya@jiofinance.in", roles=["super_admin"]),
        IamUserRole(email="new.user@jiofinance.in", roles=["legal_admin"]),
    ]
    mock_iam = AsyncMock()
    mock_iam.configured = True
    mock_iam.resolve_all_users = AsyncMock(return_value=iam_users)

    result = await sync_all_users_from_iam(db, iam=mock_iam)

    assert result.created == 1
    assert result.updated == 1
    assert result.deactivated == 1

    users = {u.email: u for u in db.execute(select(User)).scalars().all()}
    assert users["vikas.maurya@jiofinance.in"].role == Role.SUPER_ADMIN.value
    assert users["vikas.maurya@jiofinance.in"].iam_managed is True
    assert users["new.user@jiofinance.in"].role == Role.LEGAL_ADMIN.value
    assert users["removed@jiofinance.in"].is_active is False


@pytest.mark.asyncio
async def test_sync_single_user_deactivates_when_missing_from_iam(db: Session) -> None:
    user = User(
        email="gone@jiofinance.in",
        full_name="Gone",
        hashed_password=hash_password("x"),
        role=Role.LEGAL_USER.value,
        is_active=True,
        iam_managed=True,
    )
    db.add(user)
    db.commit()

    mock_iam = AsyncMock()
    mock_iam.configured = True
    mock_iam.resolve_user = AsyncMock(return_value=None)

    updated = await sync_user_from_iam(db, "gone@jiofinance.in", iam=mock_iam)
    assert updated is not None
    assert updated.is_active is False
