import asyncio
import uuid

# Background jobs for the slow, off-request-path work (M1 classification, library
# ingest, M2 vendor DD). These used to be Celery tasks dispatched over Redis; they
# are now scheduled via FastAPI BackgroundTasks (see the api/v1 routes), so no
# broker or separate worker process is needed. FastAPI runs these sync functions
# in its threadpool, so the fresh event loop each opens never contends with the
# API's main loop. Each opens its own DB session because the request's session is
# already closed by the time the task runs.


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def run_classification_bg(job_id: str, actor_id: str | None = None):
    async def _inner():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.services.classification_service import ClassificationService

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as db:
                svc = ClassificationService(db)
                await svc.run_classification(uuid.UUID(job_id), uuid.UUID(actor_id) if actor_id else None)
                await db.commit()
        finally:
            await engine.dispose()

    return _run_async(_inner())


def ingest_library_document_bg(document_id: str):
    """Runs the slow extract/chunk step for a RegulationDocument that
    library.py's upload route already created (status='processing') and
    committed — the task only needs the id, it reads pdf_bytes back from the
    row rather than round-tripping the file through a message broker."""

    async def _inner():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.services.library_service import LibraryService

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as db:
                svc = LibraryService(db)
                document = await svc.process_document(uuid.UUID(document_id))
                await db.commit()
                return str(document.id)
        finally:
            await engine.dispose()

    return _run_async(_inner())


def run_vendor_dd_bg(report_id: str):
    async def _inner():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import get_settings
        from app.services.vendor_service import VendorService

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as db:
                svc = VendorService(db)
                report = await svc.run_dd(uuid.UUID(report_id))
                await db.commit()
                return str(report.id)
        finally:
            await engine.dispose()

    return _run_async(_inner())
