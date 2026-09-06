"""Idempotent user bootstrap for local / Docker demos.

    python -m app.scripts.bootstrap_users
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.auth import hash_password
from app.core.config import get_settings
from app.models.user import User, UserRole

ACCOUNTS: list[tuple[str, str, list[str]]] = [
    ("admin@genaiforge.local", "System Admin", ["admin"]),
    ("manager@genaiforge.local", "Platform User", ["user"]),
    ("demo@genaiforge.local", "Demo Analyst", ["admin", "user"]),
]


async def bootstrap() -> None:
    settings = get_settings()
    password = settings.seed_password
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        for email, name, desired_roles in ACCOUNTS:
            result = await db.execute(
                select(User).options(selectinload(User.roles)).where(User.email == email)
            )
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    email=email,
                    display_name=name,
                    password_hash=hash_password(password),
                    is_active=True,
                )
                db.add(user)
                await db.flush()
                for role in desired_roles:
                    db.add(UserRole(user_id=user.id, role=role))
                print(f"Created {email} with roles={desired_roles}")
                continue
            user.password_hash = hash_password(password)
            user.is_active = True
            current = sorted(r.role for r in user.roles)
            if current != sorted(desired_roles):
                for r in list(user.roles):
                    await db.delete(r)
                await db.flush()
                for role in desired_roles:
                    db.add(UserRole(user_id=user.id, role=role))
            print(f"Set password + roles={desired_roles} for {email}")
        await db.commit()
    print(f"\nDone. Log in with the emails above and password: {password}")


if __name__ == "__main__":
    asyncio.run(bootstrap())
