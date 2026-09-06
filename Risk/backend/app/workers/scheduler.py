"""Start APScheduler for periodic form reminders."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.workers.reminder_scheduler import send_due_reminders

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def start_reminder_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(send_due_reminders, "interval", hours=24, id="form_reminders")
    _scheduler.start()
    logger.info("Form reminder scheduler started")
    return _scheduler


def stop_reminder_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
