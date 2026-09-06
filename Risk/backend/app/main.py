import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

# The app had no logging configuration at all, which left the root logger with no
# handler: every logger.info/.warning/.exception in app/ went nowhere, and only
# SQLAlchemy's echo output was visible. That matters most for the email path,
# which deliberately swallows send failures so a broken SMTP config cannot roll
# back a form assignment — "it failed, check the logs" is worthless if the logs
# are empty.
#
# Safe to do at import time: uvicorn applies its own dictConfig afterwards, but
# its config declares no "root" key, so these handlers survive.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    import os
    import traceback
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    # DATABASE_URL uses async driver; alembic needs psycopg2 (sync, installed via psycopg2-binary)
    raw = os.environ.get("DATABASE_URL") or get_settings().database_url
    # Normalise any async/psycopg3 scheme to psycopg2
    sync_url = raw
    for scheme in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql://", "postgres://"):
        if sync_url.startswith(scheme):
            sync_url = "postgresql+psycopg2://" + sync_url[len(scheme):]
            break
    print(f"[migration] host: {raw.split('@')[-1].split('/')[0] if '@' in raw else raw[:40]}", flush=True)
    print(f"[migration] driver: {sync_url.split('://')[0]}", flush=True)

    # Wait for Cloud SQL proxy sidecar to be ready (it starts in parallel with the app container)
    import time
    import socket
    host = raw.split('@')[-1].split('/')[0].split(':')[0] if '@' in raw else '127.0.0.1'
    port = int(raw.split('@')[-1].split('/')[0].split(':')[1]) if '@' in raw and ':' in raw.split('@')[-1].split('/')[0] else 5432
    for attempt in range(10):
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[migration] proxy ready after {attempt}s", flush=True)
                break
        except OSError:
            print(f"[migration] waiting for proxy... attempt {attempt+1}", flush=True)
            time.sleep(2)
    else:
        print("[migration] proxy never became ready, skipping", flush=True)
        return

    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    print(f"[migration] alembic.ini path: {ini_path} exists={ini_path.exists()}", flush=True)

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")
    print("[migration] complete", flush=True)


async def _seed_users_if_needed() -> None:
    """Ensure the two canonical accounts exist on every environment.

    Creates admin@/manager@ if missing and normalises their role. Sets the default
    password ONLY when the account has none yet — so a redeploy never resets a
    password an admin has already changed. Change the seed password in .env for any
    real environment.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.core.auth import hash_password
    from app.core.database import async_session_factory
    from app.models.user import User, UserRole

    default_password = get_settings().seed_password
    accounts: list[tuple[str, str, list[str]]] = [
        ("admin@genaiforge.local", "System Admin", ["admin"]),
        ("manager@genaiforge.local", "Platform User", ["user"]),
        ("demo@genaiforge.local", "Demo Analyst", ["admin", "user"]),
    ]
    try:
        async with async_session_factory() as db:
            for email, name, desired_roles in accounts:
                result = await db.execute(
                    select(User).options(selectinload(User.roles)).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    user = User(email=email, display_name=name, password_hash=hash_password(default_password))
                    db.add(user)
                    await db.flush()
                    for role in desired_roles:
                        db.add(UserRole(user_id=user.id, role=role))
                    print(f"[seed] created user {email} ({desired_roles})", flush=True)
                    # Skip the role-diff below: this user's roles are already exactly
                    # desired_roles, and reading user.roles would lazy-load an unloaded
                    # relationship — illegal under asyncio, and it would abort the commit.
                    continue
                if not user.password_hash:
                    user.password_hash = hash_password(default_password)
                    print(f"[seed] set initial password for {email}", flush=True)
                current_roles = sorted(r.role for r in user.roles)
                if current_roles != sorted(desired_roles):
                    for r in list(user.roles):
                        await db.delete(r)
                    await db.flush()
                    for role in desired_roles:
                        db.add(UserRole(user_id=user.id, role=role))
                    print(f"[seed] set roles={desired_roles} for {email}", flush=True)
            await db.commit()
    except Exception as exc:
        print(f"[seed] could not ensure users, skipping: {exc}", flush=True)


async def _seed_clauses_if_needed() -> None:
    """Auto-ingest regulation PDFs if no v3 clauses exist yet.
    Runs once on first deploy of any environment; subsequent startups skip cheaply."""
    from pathlib import Path
    from sqlalchemy import text
    from app.core.database import async_session_factory
    from app.scripts.regulation_ingest.load_clauses import load

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM regulator_clauses WHERE version = 'v3'")
            )
            count = result.scalar() or 0
    except Exception as exc:
        print(f"[seed] could not check clause count, skipping: {exc}", flush=True)
        return

    if count > 0:
        print(f"[seed] {count} v3 clauses already loaded, skipping", flush=True)
        return

    print("[seed] no v3 clauses found — ingesting regulation PDFs", flush=True)
    base = Path(__file__).resolve().parents[1] / "resources" / "regulations"

    specs = [
        (
            base / "rbi_nbfc_outsourcing_2025.pdf", "RBI", "NBFC",
            "RBI (NBFC - Managing Risks in Outsourcing) Directions, 2025", "RBI-NBFC-2025",
        ),
        (
            base / "rbi_payments_bank_outsourcing_2025.pdf", "RBI", "PAYMENTS_BANK",
            "RBI (Payments Banks - Managing Risks in Outsourcing) Directions, 2025", "RBI-PB-2025",
        ),
        (
            base / "sebi_ia_master_circular_2025.pdf", "SEBI", "IA",
            "SEBI Master Circular for Investment Advisers, 2025", "SEBI-MC-IA-2025",
        ),
    ]

    for pdf_path, regulator, instrument, source_doc, ref_prefix in specs:
        if not pdf_path.exists():
            print(f"[seed] PDF not found: {pdf_path.name}, skipping", flush=True)
            continue
        try:
            n = await load(str(pdf_path), regulator, instrument, source_doc, ref_prefix, "v3")
            print(f"[seed] loaded {n} clauses — {regulator}/{instrument}", flush=True)
        except Exception as exc:
            print(f"[seed] failed {regulator}/{instrument}: {exc}", flush=True)

    print("[seed] ingestion complete", flush=True)


async def _seed_prompts_if_needed() -> None:
    """Sync the editable M1 classification guidance (one active row per regulator)
    with the in-code defaults on startup:
      - no row yet             -> insert v1 (active)
      - active row up to date  -> no-op (the normal case on every restart)
      - code text changed      -> insert a new version (active) and deactivate the
                                  previous active row, in one transaction

    This makes a deploy of new prompt code propagate to the DB automatically while
    preserving version history for the audit trail (which prompt classified what).
    The DB remains the source of truth at classify time; the in-code text is the
    thing operators edit. Do NOT hand-edit rows in a deployed DB — a later deploy
    will supersede the change. Exactly one row stays active per name, which the
    classify query relies on (it does limit(1) with no ORDER BY)."""
    import re
    from sqlalchemy import select
    from app.adapters.ai.gemini_llm import (
        DEFAULT_GUIDANCE_RBI,
        DEFAULT_GUIDANCE_SEBI,
        PROMPT_VERSION,
    )
    from app.core.database import async_session_factory
    from app.models.config import PromptTemplate

    rows = {"M1_RBI": DEFAULT_GUIDANCE_RBI, "M1_SEBI": DEFAULT_GUIDANCE_SEBI}
    try:
        async with async_session_factory() as session:
            for name, text in rows.items():
                result = await session.execute(
                    select(PromptTemplate).where(
                        PromptTemplate.module == "M1", PromptTemplate.name == name
                    )
                )
                versions = result.scalars().all()
                active = next((r for r in versions if r.is_active), None)
                if active is not None and active.template_text == text:
                    continue  # DB already matches the code — nothing to do

                # Next version label = highest existing vN + 1 (v1 on first seed).
                highest = max(
                    (int(m.group(1)) for r in versions
                     if (m := re.match(r"v(\d+)$", r.version or ""))),
                    default=0,
                )
                next_version = f"v{highest + 1}"

                for r in versions:
                    r.is_active = False  # only the new row stays active
                session.add(
                    PromptTemplate(
                        module="M1", name=name, version=next_version,
                        template_text=text, is_active=True,
                    )
                )
                action = "created v1" if not versions else f"upgraded to {next_version}"
                print(f"[seed] prompt {name} {action}", flush=True)
            await session.commit()
    except Exception as exc:
        print(f"[seed] could not sync prompts, skipping: {exc}", flush=True)


async def _seed_form_template_if_needed() -> None:
    """Import the repo-root VDD Excel template when no active form exists."""
    from pathlib import Path
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.models.form import FormTemplate
    from app.services.form_import import parse_vdd_sheet2
    from app.services.form_service import FormService

    async with async_session_factory() as db:
        result = await db.execute(select(FormTemplate).where(FormTemplate.is_active.is_(True)).limit(1))
        if result.scalar_one_or_none():
            return
        candidates = [
            Path(__file__).resolve().parents[2] / "1 Vendor Due Diligence - [Vendor Name].xlsx",
        ]
        if len(Path(__file__).resolve().parents) > 3:
            candidates.append(
                Path(__file__).resolve().parents[3] / "1 Vendor Due Diligence - [Vendor Name].xlsx"
            )
        xlsx = next((p for p in candidates if p.is_file()), None)
        if xlsx is None:
            print("[seed] VDD xlsx not found, skipping form template import", flush=True)
            return
        parsed = parse_vdd_sheet2(xlsx.read_bytes())
        await FormService(db).create_template(parsed["name"], parsed["schema"], created_by=None)
        await db.commit()
        print("[seed] imported VDD form template from xlsx", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings come exclusively from .env / process environment.
    get_settings.cache_clear()
    try:
        _run_migrations()
    except Exception as exc:
        import traceback
        print(f"[migration] FAILED: {exc}", flush=True)
        traceback.print_exc()
    try:
        await _seed_users_if_needed()
    except Exception as exc:
        import traceback
        print(f"[seed] users FAILED: {exc}", flush=True)
        traceback.print_exc()
    try:
        await _seed_clauses_if_needed()
    except Exception as exc:
        import traceback
        print(f"[seed] FAILED: {exc}", flush=True)
        traceback.print_exc()
    try:
        await _seed_prompts_if_needed()
    except Exception as exc:
        import traceback
        print(f"[seed] prompts FAILED: {exc}", flush=True)
        traceback.print_exc()
    try:
        from app.scripts.regulation_ingest.backfill_documents import backfill
        await backfill()
    except Exception as exc:
        import traceback
        print(f"[backfill] FAILED: {exc}", flush=True)
        traceback.print_exc()
    try:
        await _seed_form_template_if_needed()
    except Exception as exc:
        print(f"[seed] form template FAILED: {exc}", flush=True)
    from app.workers.scheduler import start_reminder_scheduler
    start_reminder_scheduler()
    yield
    from app.workers.scheduler import stop_reminder_scheduler
    stop_reminder_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GenAIForge Risk API",
        version="1.0.0",
        description="GenAIForge risk & vendor due-diligence showcase platform",
        lifespan=lifespan,
    )
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
