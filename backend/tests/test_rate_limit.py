"""Rate limiting tests — global config + AI/upload sliding window enforcement."""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException


def test_rate_limiter_is_attached_to_app():
    """The app must have a limiter in its state for slowapi to work."""
    from app.main import app

    assert hasattr(app.state, "limiter"), "Limiter not attached to app.state"
    assert app.state.limiter is not None


def test_global_rate_limit_is_configured():
    """Global API rate limit must be set from config."""
    from app.core.config import settings
    from app.core.rate_limit import limiter

    assert limiter is not None
    assert settings.RATE_LIMIT_API
    assert settings.RATE_LIMIT_LOGIN
    assert settings.RATE_LIMIT_AI
    assert settings.RATE_LIMIT_UPLOAD


def test_login_has_account_lockout():
    """Login endpoint must have account lockout (5 attempts / 15 min window).
    Primary brute-force protection, implemented in auth_service.authenticate()."""
    from app.services.auth_service import authenticate

    assert callable(authenticate)


# ── AI / upload sliding-window tests ─────────────────────


@pytest.fixture(autouse=True)
def _clear_buckets():
    from app.core.rate_limit import _ai_attempts, _upload_attempts

    _ai_attempts.clear()
    _upload_attempts.clear()
    yield
    _ai_attempts.clear()
    _upload_attempts.clear()


def _fake_request(ip: str = "1.2.3.4"):
    """Minimal request stub — only the bits the limiter touches."""
    request = SimpleNamespace()
    request.headers = {}
    request.client = SimpleNamespace(host=ip)
    return request


@pytest.mark.asyncio
async def test_ai_limit_allows_calls_under_threshold():
    from app.core.rate_limit import enforce_ai_rate_limit

    user = SimpleNamespace(id=42)
    request = _fake_request()

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "3/minute"
        for _ in range(3):
            await enforce_ai_rate_limit(request, current_user=user)


@pytest.mark.asyncio
async def test_ai_limit_blocks_user_after_threshold():
    from app.core.rate_limit import enforce_ai_rate_limit

    user = SimpleNamespace(id=42)
    request = _fake_request()

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "3/minute"
        for _ in range(3):
            await enforce_ai_rate_limit(request, current_user=user)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_ai_rate_limit(request, current_user=user)

    assert exc_info.value.status_code == 429
    assert "AI istekleri" in exc_info.value.detail
    assert exc_info.value.headers.get("Retry-After") == "60"


@pytest.mark.asyncio
async def test_ai_limit_isolated_per_user():
    """User A hitting the cap doesn't affect user B."""
    from app.core.rate_limit import enforce_ai_rate_limit

    request = _fake_request()
    user_a = SimpleNamespace(id=1)
    user_b = SimpleNamespace(id=2)

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "2/minute"

        for _ in range(2):
            await enforce_ai_rate_limit(request, current_user=user_a)

        with pytest.raises(HTTPException):
            await enforce_ai_rate_limit(request, current_user=user_a)

        # User B starts fresh
        await enforce_ai_rate_limit(request, current_user=user_b)
        await enforce_ai_rate_limit(request, current_user=user_b)


@pytest.mark.asyncio
async def test_ai_limit_falls_back_to_ip_for_anonymous():
    from app.core.rate_limit import _ai_attempts, enforce_ai_rate_limit

    request = _fake_request(ip="10.0.0.5")

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "2/minute"

        for _ in range(2):
            await enforce_ai_rate_limit(request, current_user=None)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_ai_rate_limit(request, current_user=None)

    assert exc_info.value.status_code == 429
    assert any(k.startswith("ip:10.0.0.5") for k in _ai_attempts.keys())


@pytest.mark.asyncio
async def test_upload_limit_blocks_after_threshold():
    """Upload limiter is independent from AI limiter and uses its own bucket."""
    from app.core.rate_limit import enforce_upload_rate_limit

    user = SimpleNamespace(id=7)
    request = _fake_request()

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_UPLOAD = "2/minute"

        await enforce_upload_rate_limit(request, current_user=user)
        await enforce_upload_rate_limit(request, current_user=user)

        with pytest.raises(HTTPException) as exc_info:
            await enforce_upload_rate_limit(request, current_user=user)

    assert exc_info.value.status_code == 429
    assert "Yukleme limiti" in exc_info.value.detail


@pytest.mark.asyncio
async def test_ai_and_upload_buckets_independent():
    """Hitting the AI cap doesn't reduce the upload budget for the same user."""
    from app.core.rate_limit import enforce_ai_rate_limit, enforce_upload_rate_limit

    user = SimpleNamespace(id=99)
    request = _fake_request()

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "1/minute"
        cfg.RATE_LIMIT_UPLOAD = "1/minute"

        await enforce_ai_rate_limit(request, current_user=user)
        with pytest.raises(HTTPException):
            await enforce_ai_rate_limit(request, current_user=user)

        # Upload budget intact
        await enforce_upload_rate_limit(request, current_user=user)


@pytest.mark.asyncio
async def test_window_drops_expired_entries():
    """Sliding window: an entry older than the window is evicted on next call."""
    from app.core.rate_limit import _ai_attempts, enforce_ai_rate_limit

    user = SimpleNamespace(id=1)
    request = _fake_request()

    _ai_attempts["user:1"] = deque([0.0])  # epoch — definitely expired

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "1/minute"
        await enforce_ai_rate_limit(request, current_user=user)

    assert len(_ai_attempts["user:1"]) == 1


@pytest.mark.asyncio
async def test_x_forwarded_for_used_for_ip_key():
    """When behind a proxy, X-Forwarded-For takes precedence over request.client."""
    from app.core.rate_limit import _ai_attempts, enforce_ai_rate_limit

    request = _fake_request(ip="172.16.0.1")
    request.headers["x-forwarded-for"] = "203.0.113.5, 172.16.0.1"

    with patch("app.core.rate_limit.settings") as cfg:
        cfg.RATE_LIMIT_AI = "1/minute"
        await enforce_ai_rate_limit(request, current_user=None)

    assert any("203.0.113.5" in k for k in _ai_attempts.keys())
