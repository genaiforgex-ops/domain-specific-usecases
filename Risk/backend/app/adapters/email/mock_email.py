import logging
import uuid

logger = logging.getLogger(__name__)


class MockEmailAdapter:
    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        *,
        cc: list[str] | None = None,
        html: str | None = None,
    ) -> str:
        msg_id = f"mock-email-{uuid.uuid4()}"
        logger.info(
            "[mock-email] to=%s cc=%s subject=%s html=%s body=%s id=%s",
            to,
            cc or [],
            subject,
            "yes" if html else "no",
            body[:200],
            msg_id,
        )
        return msg_id
