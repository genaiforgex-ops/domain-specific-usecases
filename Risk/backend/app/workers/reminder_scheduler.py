"""Daily reminder job for overdue form assignments."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_factory
from app.models.form import FormAssignment
from app.services.form_service import FormService

logger = logging.getLogger(__name__)


async def send_due_reminders() -> None:
    now = datetime.now(timezone.utc)
    window = now + timedelta(days=2)
    cutoff = now - timedelta(hours=24)

    async with async_session_factory() as db:
        result = await db.execute(
            select(FormAssignment)
            .options(selectinload(FormAssignment.template))
            .where(
                FormAssignment.status.in_(("assigned", "in_progress")),
                FormAssignment.due_at.isnot(None),
                FormAssignment.due_at <= window,
            )
        )
        assignments = list(result.scalars().all())
        svc = FormService(db)
        sent = 0
        for assignment in assignments:
            if assignment.last_reminder_at and assignment.last_reminder_at > cutoff:
                continue
            if assignment.due_at and assignment.due_at < now:
                assignment.status = "overdue"
            try:
                await svc.send_reminder(assignment)
                sent += 1
            except Exception:
                logger.exception("Failed to send reminder for assignment %s", assignment.id)
        if sent:
            await db.commit()
            logger.info("Sent %d form reminders", sent)
