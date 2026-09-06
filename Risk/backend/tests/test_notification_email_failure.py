"""Unit tests for NotificationService's mail guard.

Covers the one property that matters: a broken SMTP config must not take the
caller's transaction down with it. Every caller (form submit, assignment) runs
inside the request transaction before the endpoint commits, so an SMTP error
propagating out of notify() rolled the whole request back — a form submission
was lost on dev because Gmail rejected the credentials.

The notification row itself and the admin fan-out query need a database, and the
repo has no DB fixtures, so those are covered by the manual verification steps.
Here the session and the email adapter are both stubbed.
"""
import asyncio
import uuid

import pytest

from app.services import notification_service
from app.services.notification_service import NotificationService


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Just enough AsyncSession for notify() — no database involved."""

    def __init__(self, email="admin@genaiforge.local"):
        self._email = email
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        pass

    async def refresh(self, row):
        pass

    async def execute(self, _stmt):
        return _Result(self._email)


class _ExplodingAdapter:
    def __init__(self):
        self.calls = 0

    async def send(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("(535, b'5.7.8 Username and Password not accepted')")


@pytest.fixture
def exploding_email(monkeypatch):
    adapter = _ExplodingAdapter()
    monkeypatch.setattr(notification_service, "get_email_adapter", lambda: adapter)
    return adapter


def test_a_failing_smtp_send_does_not_reach_the_caller(exploding_email):
    db = _FakeSession()
    svc = NotificationService(db)

    row = asyncio.run(
        svc.notify(uuid.uuid4(), title="Form submitted for classification", body="…")
    )

    assert exploding_email.calls == 1, "the adapter should have been tried"
    assert row is not None, "the notification must still be returned"
    assert len(db.added) == 1, "the notification row must still be written"


def test_the_notification_is_still_written_when_mail_is_broken(exploding_email):
    db = _FakeSession()
    svc = NotificationService(db)

    asyncio.run(svc.notify(uuid.uuid4(), title="Assigned", body="b", link="/my-forms"))

    (row,) = db.added
    assert row.title == "Assigned"
    assert row.link == "/my-forms"


def test_send_email_false_skips_the_adapter_entirely(exploding_email):
    db = _FakeSession()
    svc = NotificationService(db)

    asyncio.run(svc.notify(uuid.uuid4(), title="Quiet", send_email=False))

    assert exploding_email.calls == 0


def test_a_user_with_no_email_address_is_not_mailed(exploding_email):
    db = _FakeSession(email=None)
    svc = NotificationService(db)

    asyncio.run(svc.notify(uuid.uuid4(), title="No address"))

    assert exploding_email.calls == 0
    assert len(db.added) == 1
