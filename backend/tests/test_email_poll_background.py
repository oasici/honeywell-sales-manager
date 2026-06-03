"""Tests for the deferred /poll parsing (fast button → background parse).

``/poll`` now fetches + persists inline and defers the per-email Claude
parse to ``_parse_fetched_emails_bg``, which runs on its own session,
commits per email, and paces calls by ``EMAIL_BATCH_DELAY_SECONDS``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.emails import _parse_fetched_emails_bg
from app.core.config import settings


class _FakeSessionCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_bg_parse_processes_all_commits_and_paces(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BATCH_DELAY_SECONDS", 1.0)
    db = AsyncMock()
    db.commit = AsyncMock()
    svc = MagicMock()
    svc.process_email = AsyncMock()

    with patch("app.core.database.async_session", lambda: _FakeSessionCM(db)), \
         patch("app.services.email_processing_service.EmailProcessingService", return_value=svc), \
         patch("asyncio.sleep", new=AsyncMock()) as fake_sleep:
        await _parse_fetched_emails_bg([10, 11, 12])

    assert svc.process_email.await_count == 3
    assert [c.args[0] for c in svc.process_email.await_args_list] == [10, 11, 12]
    assert db.commit.await_count == 3
    # paced between the three, not after the last
    assert fake_sleep.await_count == 2


@pytest.mark.asyncio
async def test_bg_parse_continues_after_one_failure(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BATCH_DELAY_SECONDS", 0.0)
    db = AsyncMock()
    db.commit = AsyncMock()
    svc = MagicMock()
    svc.process_email = AsyncMock(side_effect=[None, RuntimeError("boom"), None])

    with patch("app.core.database.async_session", lambda: _FakeSessionCM(db)), \
         patch("app.services.email_processing_service.EmailProcessingService", return_value=svc), \
         patch("asyncio.sleep", new=AsyncMock()):
        await _parse_fetched_emails_bg([1, 2, 3])

    assert svc.process_email.await_count == 3       # all attempted
    assert db.commit.await_count == 2               # commit skipped for the failed one


@pytest.mark.asyncio
async def test_bg_parse_empty_is_noop():
    # no ids -> no session work, no error
    await _parse_fetched_emails_bg([])
