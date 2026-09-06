"""Show exactly which M1 prompt the running app would use, and whether it is
the upgraded version. Read-only — makes no changes.

    python -m app.scripts.inspect_prompt

Use this to settle "why isn't my prompt change showing?": it prints the target
database, whether the M1_RBI / M1_SEBI rows exist, and whether their text
contains the newest section markers. If it says NEW here but the UI still shows
the old reasoning, the classification job you are viewing was created BEFORE
the change (reasoning is frozen per job) — run a brand-new assessment.
"""
import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.config import PromptTemplate

# A phrase that only exists in the upgraded reasoning format.
NEW_MARKER = "Why not the alternatives"


def _masked_db() -> str:
    from app.core.config import get_settings

    url = get_settings().database_url
    return url.rsplit("@", 1)[-1] if "@" in url else url


async def inspect() -> None:
    print(f"[inspect] target DB: {_masked_db()}\n")
    async with async_session_factory() as session:
        for name in ("M1_RBI", "M1_SEBI"):
            result = await session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.module == "M1",
                    PromptTemplate.name == name,
                    PromptTemplate.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                print(f"{name}: NO ACTIVE ROW → app falls back to the in-code default")
                continue
            version = "NEW ✅" if NEW_MARKER in row.template_text else "OLD ❌"
            print(f"\n===== {name} (reasoning format: {version}) =====")
            print(row.template_text)
            print("=" * (12 + len(name)))


if __name__ == "__main__":
    asyncio.run(inspect())
