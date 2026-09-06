"""FastAPI entry — CORS, router registration, startup migrations and seeding.

Schema is owned by Alembic (`backend/alembic/versions`). On startup the app runs
`alembic upgrade head` (unless RUN_MIGRATIONS_ON_STARTUP=false), so the schema
always matches the code however the app is launched, then seeds role accounts.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    admin_users,
    agent_prompts,
    approvals,
    auth,
    banner_templates,
    banners,
    briefs,
    figma_auth,
    image_prompts,
    notifications,
    users,
)
from app.config import settings
from app.database import SessionLocal
from app.services import approval_links
from app.services.seed_service import seed_users

logger = logging.getLogger("uvicorn.error")


def _configure_logging() -> None:
    """Surface application logs (the ``app.*`` hierarchy) in the server console.

    Uvicorn only configures its own loggers, so without this our ``INFO`` logs —
    including email send results — are silently dropped, and the app looks
    "silent" even when it's working. Route ``app`` through uvicorn's handlers
    (or a plain stream handler when the app is run without uvicorn)."""
    app_logger = logging.getLogger("app")
    if app_logger.handlers:  # already configured (e.g. on reload) — leave as-is
        return
    handlers = logging.getLogger("uvicorn.error").handlers
    if not handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        handlers = [stream]
    for h in handlers:
        app_logger.addHandler(h)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


def _upgrade_db() -> None:
    """Bring the database up to the latest migration (alembic upgrade head).
    Uses absolute paths so it works regardless of the process's working dir."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    backend_dir = Path(__file__).resolve().parents[1]  # .../backend
    cfg = AlembicConfig(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_migrations_on_startup:
        logger.info("Applying database migrations (alembic upgrade head)…")
        _upgrade_db()
        logger.info("Database schema is up to date.")
    # Configure app logging AFTER migrations: alembic's fileConfig reconfigures
    # the logging system, so setting this up earlier would be undone.
    _configure_logging()
    email = settings.email
    has_creds = bool(email.smtp_username and email.smtp_password)
    logger.info(
        "Email notifications %s (from=%s, smtp=%s:%s, auth=%s)",
        "ENABLED" if email.enabled else "DISABLED",
        email.from_address or "<unset>",
        email.smtp_host,
        email.smtp_port,
        "credentials present" if has_creds else "NO CREDENTIALS",
    )
    if email.enabled and not has_creds:
        logger.warning(
            "EMAIL_SMTP_USERNAME/PASSWORD are empty — SMTP AUTH will be skipped and "
            "Gmail rejects sends with '530 Authentication Required'. Set them in .env "
            "(or the K8s gf-secret) when email notifications are required."
        )
    # Fail fast rather than mail one-click approval links signed with an empty key.
    # Only when email is on: with notifications disabled no link is ever minted, so
    # a local run without the secret is fine.
    if email.enabled:
        approval_links.check_configured()
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            n = seed_users(db)
            if n:
                logger.info("Seeded %d demo role account(s)", n)
        finally:
            db.close()
    yield


app = FastAPI(title="GenAIForge Marketing API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(briefs.router)
app.include_router(approvals.router)
app.include_router(banners.router)
app.include_router(banner_templates.router)
app.include_router(image_prompts.router)
app.include_router(agent_prompts.router)
app.include_router(admin.router)
app.include_router(admin_users.router)
app.include_router(figma_auth.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
