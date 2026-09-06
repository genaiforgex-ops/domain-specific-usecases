import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.factory import get_email_adapter
from app.models.notification import Notification
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        body: str | None = None,
        link: str | None = None,
        send_email: bool = True,
    ) -> Notification:
        row = Notification(user_id=user_id, title=title, body=body, link=link)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)

        if send_email:
            result = await self.db.execute(select(User.email).where(User.id == user_id))
            email_addr = result.scalar_one_or_none()
            if email_addr:
                # Never let a mail failure reach the caller. Every caller runs
                # inside the request transaction before the endpoint commits, so
                # an SMTP error used to 500 the request and roll the whole thing
                # back — a form submission was lost because the email announcing
                # it could not be sent. The row above is the notification that
                # matters; it is already flushed and the user sees it in-app.
                # Mirrors FormService._send_mail_safe, which learned this first.
                try:
                    adapter = get_email_adapter()
                    msg_id = await adapter.send([email_addr], subject=title, body=body or title)
                    logger.info("Email sent to %s: %s", email_addr, msg_id)
                except Exception:
                    logger.exception("Notification email FAILED to=%s subject=%s", email_addr, title)
        return row

    async def notify_admins(
        self,
        *,
        title: str,
        body: str | None = None,
        link: str | None = None,
    ) -> list[Notification]:
        result = await self.db.execute(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role == "admin", User.is_active.is_(True))
        )
        rows: list[Notification] = []
        for (admin_id,) in result.all():
            rows.append(
                await self.notify(admin_id, title=title, body=body, link=link, send_email=True)
            )
        return rows
