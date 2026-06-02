"""Batch email-parse throttle tests.

``batch_process_pending_emails`` paces its Claude calls to stay under the
org's per-minute token budget: a configurable delay between each parse,
skipped after the last one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.tasks.scheduler as sched
from app.core.config import settings


class _FakeSessionCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


def _fake_db(emails):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = emails
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_throttle_sleeps_between_emails_not_after_last(monkeypatch):
    emails = [MagicMock(id=i) for i in range(3)]
    db = _fake_db(emails)

    monkeypatch.setattr(settings, "EMAIL_BATCH_DELAY_SECONDS", 2.0)
    monkeypatch.setattr(settings, "EMAIL_BATCH_SIZE", 50)

    svc = MagicMock()
    svc.process_email = AsyncMock()

    with patch("app.core.database.async_session", lambda: _FakeSessionCM(db)), \
         patch("app.services.email_processing_service.EmailProcessingService", return_value=svc), \
         patch.object(sched.asyncio, "sleep", new=AsyncMock()) as fake_sleep:
        await sched.batch_process_pending_emails()

    assert svc.process_email.await_count == 3
    # 3 emails -> 2 inter-email sleeps (none after the last)
    assert fake_sleep.await_count == 2
    fake_sleep.assert_awaited_with(2.0)


@pytest.mark.asyncio
async def test_zero_delay_disables_throttle(monkeypatch):
    emails = [MagicMock(id=i) for i in range(3)]
    db = _fake_db(emails)

    monkeypatch.setattr(settings, "EMAIL_BATCH_DELAY_SECONDS", 0.0)

    svc = MagicMock()
    svc.process_email = AsyncMock()

    with patch("app.core.database.async_session", lambda: _FakeSessionCM(db)), \
         patch("app.services.email_processing_service.EmailProcessingService", return_value=svc), \
         patch.object(sched.asyncio, "sleep", new=AsyncMock()) as fake_sleep:
        await sched.batch_process_pending_emails()

    assert svc.process_email.await_count == 3
    assert fake_sleep.await_count == 0  # no pacing when delay is 0


@pytest.mark.asyncio
async def test_failed_email_still_paces_and_continues(monkeypatch):
    emails = [MagicMock(id=i) for i in range(3)]
    db = _fake_db(emails)

    monkeypatch.setattr(settings, "EMAIL_BATCH_DELAY_SECONDS", 1.5)

    svc = MagicMock()
    # middle email raises — the loop must continue and still pace.
    svc.process_email = AsyncMock(side_effect=[None, RuntimeError("boom"), None])

    with patch("app.core.database.async_session", lambda: _FakeSessionCM(db)), \
         patch("app.services.email_processing_service.EmailProcessingService", return_value=svc), \
         patch.object(sched.asyncio, "sleep", new=AsyncMock()) as fake_sleep:
        await sched.batch_process_pending_emails()

    assert svc.process_email.await_count == 3
    assert fake_sleep.await_count == 2
    db.commit.assert_awaited_once()
