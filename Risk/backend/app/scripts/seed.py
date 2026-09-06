"""Seed database with demo users, clauses, and config."""
import asyncio
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import hash_password
from app.core.config import get_settings
from app.core.database import Base
from app.models.config import ModuleAIConfig, PromptTemplate
from app.models.control import Control, ControlTest
from app.models.scoring import ScoringConfig
from app.models.user import User, UserRole
from app.models.vendor import DDWeightConfig, Vendor

# Default password for the two seeded accounts — change it immediately after first
# login (or via User Management). Only two roles exist now: admin and user.
DEFAULT_PASSWORD = "demo1234"
USERS = [
    ("admin@genaiforge.local", "System Admin", ["admin"]),
    ("manager@genaiforge.local", "Platform User", ["user"]),
    ("demo@genaiforge.local", "Demo Analyst", ["admin", "user"]),
]

FACTOR_WEIGHTS = {
    "customer_impact": 1.2,
    "data_sensitivity": 1.5,
    "transaction_volume": 1.0,
    "vendor_dependency": 1.1,
    "regulatory_exposure": 1.4,
    "technology_complexity": 0.9,
}

DD_WEIGHTS = {
    "litigation": 1.5,
    "regulatory_action": 2.0,
    "adverse_media": 1.0,
    "financial_distress": 1.8,
    "sanctions": 3.0,
    "ownership": 1.2,
}


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        existing = await db.execute(select(User).limit(1))
        if existing.scalar_one_or_none():
            print("Database already seeded.")
            return

        for email, name, roles in USERS:
            user = User(email=email, display_name=name, password_hash=hash_password(DEFAULT_PASSWORD))
            db.add(user)
            await db.flush()
            for role in roles:
                db.add(UserRole(user_id=user.id, role=role))

        # Regulator clauses are NOT seeded here — the real library is ingested
        # from the official PDFs on startup (see _seed_clauses_if_needed in
        # app/main.py), tagged version "v3". The old hand-typed v1 demo clauses
        # were removed once that pipeline was in place.

        # Editable per-regulator classification guidance. Kept in sync with the
        # startup seeder (_seed_prompts_if_needed); the adapter falls back to
        # these same defaults in code if the rows are ever missing.
        from app.adapters.ai.gemini_llm import (
            DEFAULT_GUIDANCE_RBI,
            DEFAULT_GUIDANCE_SEBI,
            PROMPT_VERSION,
        )

        for name, template in (("M1_RBI", DEFAULT_GUIDANCE_RBI), ("M1_SEBI", DEFAULT_GUIDANCE_SEBI)):
            db.add(
                PromptTemplate(
                    module="M1", name=name, version=PROMPT_VERSION,
                    template_text=template, is_active=True,
                )
            )

        for module in ("M1", "M2", "M3"):
            db.add(ModuleAIConfig(module=module, kill_switch=False, confidence_threshold=0.70))

        db.add(
            DDWeightConfig(version="v1", category_weights=json.dumps(DD_WEIGHTS), is_active=True)
        )
        db.add(
            ScoringConfig(
                version="v1",
                factor_weights=json.dumps(FACTOR_WEIGHTS),
                scale_mapping=json.dumps({"max": 25, "bands": [5, 12, 20, 25]}),
                is_active=True,
            )
        )

        for cid, name in [
            ("CTRL-001", "KYC verification control"),
            ("CTRL-002", "Data encryption at rest"),
            ("CTRL-003", "Vendor SLA monitoring"),
        ]:
            db.add(Control(control_id=cid, name=name, category="operational"))

        db.add(
            Vendor(
                legal_name="Acme IT Services Pvt Ltd",
                cin="U72900MH2020PTC123456",
                pan="AABCA1234A",
                country="IN",
            )
        )
        db.add(
            Vendor(
                legal_name="Risky Ventures Ltd",
                cin="BADLITIG2020IN",
                pan="AABCR9999Z",
                country="IN",
            )
        )

        await db.commit()
        print("Seed completed successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
