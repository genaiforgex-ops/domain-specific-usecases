"""SMTP email notifications via a transactional outbox.

Domain events call ``enqueue(...)`` — a cheap INSERT in the caller's own DB
transaction that respects the user's preferences. A background worker calls
``dispatch_pending(...)`` to send queued rows over SMTP with retries. Nothing in
the request path touches the network, so an SMTP outage never breaks or slows
the action that triggered the notification.

Singleton accessor ``get_notification_service()`` mirrors ``get_gmail_service``.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.notification import (
    CATEGORY_PREF_FIELD,
    Notification,
    NotificationSetting,
)
from app.models.user import User
from app.services.audit_service import write_audit

logger = logging.getLogger("legalos.notifications")


def get_or_create_notification_settings(db: Session, user_id: int) -> NotificationSetting:
    row = db.execute(
        select(NotificationSetting).where(NotificationSetting.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        row = NotificationSetting(user_id=user_id)
        db.add(row)
        db.flush()
    return row


class NotificationService:
    # ------------------------------------------------------------------
    # Enqueue (request path — no network)
    # ------------------------------------------------------------------
    def enqueue(
        self,
        db: Session,
        *,
        user: User,
        category: str,
        subject: str,
        body_html: str,
        body_text: str,
        related_type: str | None = None,
        related_id: str | int | None = None,
    ) -> Notification | None:
        """Queue an email for `user`. Returns None (skips) when the user is
        inactive, has no email, or has opted out of this category. Does NOT
        commit — the caller's transaction owns the row."""
        if not user or not user.is_active or not user.email:
            return None
        prefs = get_or_create_notification_settings(db, user.id)
        if not prefs.email_enabled:
            return None
        pref_field = CATEGORY_PREF_FIELD.get(category)
        if pref_field and not getattr(prefs, pref_field, True):
            return None

        notif = Notification(
            user_id=user.id,
            to_email=user.email,
            category=category,
            subject=subject[:300],
            body_html=body_html,
            body_text=body_text,
            status="pending",
            related_type=related_type,
            related_id=str(related_id) if related_id is not None else None,
        )
        db.add(notif)
        db.flush()
        return notif

    def enqueue_for_users(self, db: Session, users, **kwargs) -> list[Notification]:
        out = []
        for u in users:
            n = self.enqueue(db, user=u, **kwargs)
            if n is not None:
                out.append(n)
        return out

    # ------------------------------------------------------------------
    # Dispatch (background worker — sends over SMTP)
    # ------------------------------------------------------------------
    def dispatch_pending(self, db: Session, limit: int = 20) -> int:
        """Send up to `limit` pending notifications. Returns count sent."""
        if not settings.smtp_username or not settings.smtp_password:
            logger.warning("[notifications] SMTP not configured; skipping dispatch")
            return 0

        rows = (
            db.execute(
                select(Notification)
                .where(
                    Notification.status == "pending",
                    Notification.attempts < settings.notification_max_attempts,
                )
                .order_by(Notification.created_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        if not rows:
            return 0

        sent = 0
        smtp = self._connect()
        try:
            for notif in rows:
                try:
                    self._send(smtp, notif)
                    notif.status = "sent"
                    notif.sent_at = datetime.now(timezone.utc)
                    notif.last_error = None
                    sent += 1
                    recipient = db.get(User, notif.user_id)
                    write_audit(
                        db,
                        user=recipient,
                        action_type="email_sent",
                        module="notifications",
                        input_summary=notif.subject,
                        target_id=notif.id,
                        extra={"category": notif.category, "to": notif.to_email},
                    )
                except Exception as exc:  # noqa: BLE001 — retry this row later
                    notif.attempts += 1
                    notif.last_error = str(exc)[:500]
                    if notif.attempts >= settings.notification_max_attempts:
                        notif.status = "failed"
                    logger.warning(
                        "[notifications] send failed (id=%s attempt=%s): %s",
                        notif.id,
                        notif.attempts,
                        exc,
                    )
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
        db.commit()
        return sent

    # ------------------------------------------------------------------
    # SMTP transport
    # ------------------------------------------------------------------
    def _connect(self) -> smtplib.SMTP:
        # Fail clearly instead of attempting login("","") — Gmail would return a
        # confusing 535 "Bad credentials" for empty creds.
        if not settings.smtp_username or not settings.smtp_password:
            raise RuntimeError(
                "SMTP credentials are not configured. Set SMTP_USERNAME and SMTP_PASSWORD "
                "(env or .env), or provide the Secret Manager secrets with valid GCP credentials."
            )
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        smtp.ehlo()
        if settings.smtp_use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password)
        return smtp

    def _send(self, smtp: smtplib.SMTP, notif: Notification) -> None:
        msg = EmailMessage()
        msg["Subject"] = notif.subject
        msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_address))
        msg["To"] = notif.to_email
        msg.set_content(notif.body_text)
        msg.add_alternative(notif.body_html, subtype="html")
        smtp.send_message(msg)

    def send_transactional(
        self, to_email: str, subject: str, body_html: str, body_text: str
    ) -> None:
        """Send a one-off email immediately (no outbox row, no prefs, no User needed).

        Used for invites, where the recipient may not be an active user yet.
        Raises on failure so the caller can report `email_sent=False`.
        """
        smtp = self._connect()
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_address))
            msg["To"] = to_email
            msg.set_content(body_text)
            msg.add_alternative(body_html, subtype="html")
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass

    def send_test(self, to_email: str) -> None:
        """Send a one-off test email (used to validate SMTP config)."""
        smtp = self._connect()
        try:
            msg = EmailMessage()
            msg["Subject"] = "LegalOS notifications — test"
            msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_address))
            msg["To"] = to_email
            msg.set_content("This is a test email from LegalOS notifications.")
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass


_notifier: NotificationService | None = None


def get_notification_service() -> NotificationService:
    global _notifier
    if _notifier is None:
        _notifier = NotificationService()
    return _notifier
