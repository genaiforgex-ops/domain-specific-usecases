"""Create or reset the bootstrap admin account.

Usage (from backend/):
    python -m scripts.reset_admin
    python -m scripts.reset_admin --password 'S3cret!'
    python -m scripts.reset_admin --email admin@genaiforge.in --password 'S3cret!'
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User


def reset_admin(email: str, password: str) -> str:
    handle = email.strip().lower()
    with SessionLocal() as db:
        user = db.execute(
            select(User).where(func.lower(User.email) == handle)
        ).scalars().first()
        if user is None:
            db.add(
                User(
                    email=handle,
                    full_name=settings.seed_admin_full_name,
                    role="AD",
                    hashed_password=hash_password(password),
                    is_active=True,
                )
            )
            db.commit()
            return f"created admin '{handle}' with the given password"

        user.hashed_password = hash_password(password)
        user.is_active = True
        db.commit()
        return f"reset password for existing admin '{handle}' (now active)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset the bootstrap admin.")
    parser.add_argument(
        "--email",
        default=settings.seed_admin_email,
        help="Admin email / login identity (default: settings.seed_admin_email).",
    )
    parser.add_argument(
        "--password",
        default=settings.seed_password,
        help="New password (default: settings.seed_password).",
    )
    args = parser.parse_args()

    summary = reset_admin(args.email, args.password)
    print(f"OK: {summary}")


if __name__ == "__main__":
    main()
