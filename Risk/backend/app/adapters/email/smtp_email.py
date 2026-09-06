import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

import anyio

logger = logging.getLogger(__name__)


class SMTPEmailAdapter:
    """Sends over plain SMTP with STARTTLS (the Gmail / Workspace shape: port 587).

    `smtplib` is blocking and a Gmail round-trip regularly takes seconds, so the
    socket work runs in a worker thread — awaiting it on the event loop would
    stall every other request for the duration.
    """

    def __init__(self, host: str, port: int, from_addr: str, username: str = "", password: str = ""):
        self.host = host
        self.port = port
        self.from_addr = from_addr
        self.username = username
        # Google shows app passwords grouped as "abcd efgh ijkl mnop". Pasted with
        # those spaces the login fails as a bare 535, which reads like a wrong
        # password rather than a formatting problem.
        self.password = password.replace(" ", "")

    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        *,
        cc: list[str] | None = None,
        html: str | None = None,
    ) -> str:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg_id = make_msgid()
        msg["Message-ID"] = msg_id

        # Plain text must be set first: add_alternative then makes this the
        # fallback part of a multipart/alternative rather than replacing it.
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")

        await anyio.to_thread.run_sync(self._send_sync, msg)

        # send_message derives the envelope recipients from To/Cc itself, so the
        # log has to spell out both to stay useful.
        logger.info("SMTP email sent to=%s cc=%s id=%s", to, cc or [], msg_id)
        return msg_id

    def _send_sync(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.username:
                smtp.starttls()
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
