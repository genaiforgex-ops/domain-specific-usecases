"""LegalOS FastAPI entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401 — register ORM models
from app.api import (
    audit,
    auth,
    build_studio,
    chat,
    clause_bank,
    contract_review,
    contract_templates,
    document_comparison,
    gmail,
    legal_bot,
    legal_news,
    legal_research,
    metrics,
    msa_automation,
    notifications,
    onlyoffice,
    playbook,
    regulatory_corpus,
    tasks,
    users,
)
from app.config import settings
from app.database import SessionLocal
from app.init_data import seed_all
from app.services.iam_sync_service import sync_all_users_from_iam


async def _gmail_poll_loop() -> None:
    import logging

    from sqlalchemy import select

    from app.models.gmail_credential import GmailCredential
    from app.models.user import User
    from app.services.gmail_poll_service import poll_user_gmail

    log = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(settings.gmail_poll_interval_seconds)
        if not settings.gmail_enabled:
            continue
        db = SessionLocal()
        try:
            creds = db.execute(select(GmailCredential)).scalars().all()
            for cred in creds:
                user = db.get(User, cred.user_id)
                if user:
                    try:
                        poll_user_gmail(db, user)
                    except Exception:
                        log.exception("Gmail poll failed for user_id=%s", cred.user_id)
        finally:
            db.close()


async def _notification_dispatch_loop() -> None:
    import logging

    from app.services.notification_service import get_notification_service

    log = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(settings.notification_dispatch_interval_seconds)
        if not settings.notifications_enabled:
            continue
        db = SessionLocal()
        try:
            get_notification_service().dispatch_pending(db)
        except Exception:
            log.exception("Notification dispatch cycle failed")
        finally:
            db.close()


async def _regulatory_scrape_loop() -> None:
    import logging

    from app.services.news_service import scrape_all

    log = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(settings.news_scrape_interval_seconds)
        if not settings.news_scrape_enabled:
            continue
        db = SessionLocal()
        try:
            scrape_all(db)
        except Exception:
            log.exception("Regulatory scrape cycle failed")
        finally:
            db.close()


async def _regulatory_corpus_refresh_loop() -> None:
    """Re-check the regulatory corpus against its official sources.

    Only documents with a direct official URL and a changing cadence are re-fetched;
    manual-download rows get flagged stale for the legal team instead.
    """
    import logging

    from app.services.regulatory_ingest_service import refresh_corpus

    log = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(settings.regulatory_refresh_interval_seconds)
        if not settings.regulatory_refresh_enabled:
            continue
        db = SessionLocal()
        try:
            summary = refresh_corpus(db)
            log.info("Regulatory corpus refresh: %s", summary)
        except Exception:
            log.exception("Regulatory corpus refresh cycle failed")
        finally:
            db.close()


async def _iam_sync_loop() -> None:
    import logging

    log = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(settings.iam_sync_interval_seconds)
        if not settings.iam_sync_enabled:
            continue
        db = SessionLocal()
        try:
            await sync_all_users_from_iam(db)
            db.commit()
        except Exception:
            log.exception("IAM user sync cycle failed")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema is managed by Alembic migrations — run `alembic upgrade head`
    # before/at deploy (the Docker image does this in its entrypoint).
    # Startup only seeds reference data, which is idempotent.
    db = SessionLocal()
    try:
        seed_all(db)
        if settings.iam_sync_enabled:
            import logging

            try:
                await sync_all_users_from_iam(db)
                db.commit()
            except Exception:
                logging.getLogger(__name__).exception("Startup IAM user sync failed")
    finally:
        db.close()
    # Warm the chatbot orchestrator (build runner + touch session schema) so the
    # first chat request is fast. Non-fatal: a warmup failure must not block the
    # rest of the platform from serving.
    if settings.orch_enabled:
        import logging

        try:
            from app.orchestrator.dependencies import warmup as orch_warmup

            await orch_warmup()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("Orchestrator warmup failed")
    background_tasks: list[asyncio.Task] = []
    if settings.gmail_enabled:
        background_tasks.append(asyncio.create_task(_gmail_poll_loop()))
    if settings.notifications_enabled:
        background_tasks.append(asyncio.create_task(_notification_dispatch_loop()))
    if settings.news_scrape_enabled:
        background_tasks.append(asyncio.create_task(_regulatory_scrape_loop()))
    if settings.regulatory_refresh_enabled:
        background_tasks.append(asyncio.create_task(_regulatory_corpus_refresh_loop()))
    if settings.iam_sync_enabled:
        background_tasks.append(asyncio.create_task(_iam_sync_loop()))
    yield
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="LegalOS — JFPSL Legal AI Central Platform",
    version="0.1.0",
    description=(
        "Internal Legal AI platform per BRD v1.0 (May 2025). Six modules behind a single "
        "RBAC-governed FastAPI + React surface. All AI inference is bounded to the seeded "
        "JFPSL corpus — no external LLM API is called for legal data."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "legalos-backend", "ai_backend": settings.ai_backend}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(contract_review.router)
app.include_router(document_comparison.router)
app.include_router(legal_bot.router)
if settings.orch_enabled:
    app.include_router(chat.router)
app.include_router(legal_research.router)
app.include_router(msa_automation.router)
app.include_router(onlyoffice.router)
app.include_router(contract_templates.router)
app.include_router(gmail.router)
app.include_router(legal_news.router)
app.include_router(regulatory_corpus.router)
app.include_router(audit.router)
app.include_router(metrics.router)
app.include_router(playbook.router)
app.include_router(notifications.router)
app.include_router(clause_bank.router)
app.include_router(tasks.router)
app.include_router(build_studio.router)
