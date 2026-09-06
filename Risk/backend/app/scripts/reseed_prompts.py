"""Force-refresh the M1 classification prompt rows from the in-code defaults.

The startup seeder (_seed_prompts_if_needed in app/main.py) only CREATES the
M1_RBI / M1_SEBI rows when they are missing — it never overwrites an existing
row, so an operator's manual prompt edits in a real environment are safe.

That is the wrong behaviour while iterating on the wording during development:
you change DEFAULT_GUIDANCE_* in code, restart, and see no change because the
DB copy (seeded earlier) still wins. Run this script to explicitly push the
current code defaults into the DB, overwriting whatever is there:

    python -m app.scripts.reseed_prompts

It is intentionally a separate, manual step — not something that runs on every
startup — so "refresh from code" is always a deliberate action.
"""
import asyncio

from sqlalchemy import select

from app.adapters.ai.gemini_llm import (
    DEFAULT_GUIDANCE_RBI,
    DEFAULT_GUIDANCE_SEBI,
    PROMPT_VERSION,
)
from app.core.database import async_session_factory
from app.models.config import PromptTemplate

ROWS = {"M1_RBI": DEFAULT_GUIDANCE_RBI, "M1_SEBI": DEFAULT_GUIDANCE_SEBI}


def _masked_db() -> str:
    """host/db of the target connection, credentials stripped — so you can
    confirm this script is updating the SAME database the app serves from."""
    from app.core.config import get_settings

    url = get_settings().database_url
    return url.rsplit("@", 1)[-1] if "@" in url else url


async def reseed() -> None:
    print(f"[reseed] target DB: {_masked_db()}")
    async with async_session_factory() as session:
        for name, text in ROWS.items():
            existing = await session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.module == "M1", PromptTemplate.name == name
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.template_text = text
                row.version = PROMPT_VERSION
                print(f"[reseed] updated {name} ({PROMPT_VERSION})")
            else:
                session.add(
                    PromptTemplate(
                        module="M1", name=name, version=PROMPT_VERSION,
                        template_text=text, is_active=True,
                    )
                )
                print(f"[reseed] created {name} ({PROMPT_VERSION})")
        await session.commit()
    print("[reseed] done")


if __name__ == "__main__":
    asyncio.run(reseed())
