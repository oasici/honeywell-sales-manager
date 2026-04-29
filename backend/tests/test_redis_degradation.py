"""Redis-removal contract tests.

After the Redis service was retired, ``app/core/redis_client.py`` is a
permanent no-op stub: ``get_redis()`` always returns ``None`` and
``close_redis()`` is a no-op. Callers across the codebase already
treat Redis as best-effort and fall back to in-memory state.

These tests pin three things so a future "let's flip Redis back on"
diff doesn't quietly break the contract:

1. ``get_redis()`` returns ``None`` regardless of ``REDIS_URL``.
2. ``/api/health`` does NOT advertise a ``redis`` field — operators
   shouldn't see a phantom dependency that doesn't exist.
3. JWT revocation, the most security-sensitive Redis caller, keeps
   working through its in-memory fallback.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ─────────────────────── stub contract ───────────────────────────────


def test_get_redis_always_returns_none():
    """``get_redis()`` is a permanent no-op stub.

    The redis_client module's docstring is the canonical reference;
    this test guards the contract so a sneaky reintroduction of a
    real Redis client doesn't slip in without the operator decision
    being made explicitly.
    """
    from app.core.redis_client import get_redis

    assert get_redis() is None


def test_get_redis_ignores_redis_url_setting(monkeypatch):
    """Even if someone sets REDIS_URL=... in env, the stub stays a stub."""
    from app.core import redis_client
    from app.core.config import settings

    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    assert redis_client.get_redis() is None


@pytest.mark.asyncio
async def test_close_redis_is_noop():
    """Lifespan close-path must not raise; it's just symmetry now."""
    from app.core.redis_client import close_redis

    # Awaitable, returns None, no exception.
    result = await close_redis()
    assert result is None


# ─────────────────────── health endpoint ─────────────────────────────


@pytest.mark.asyncio
async def test_health_endpoint_does_not_report_redis(client: AsyncClient):
    """``/api/health`` payload must not advertise a ``redis`` dependency.

    Reporting a dependency we don't have is worse than reporting
    nothing — it confuses operators looking at the dashboard.
    """
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "redis" not in body.get("checks", {})


# ─────────────────────── JWT revocation in-memory fallback ───────────


@pytest.mark.asyncio
async def test_token_revocation_uses_memory_fallback():
    """JWT revocation must keep working without Redis.

    The security path is the highest-stakes Redis caller — a token
    revocation that silently no-ops would be a real auth bug. The
    in-memory fallback (``_revoke_memory`` / ``_is_revoked_memory``)
    catches that case.
    """
    from app.core.security import (
        create_access_token,
        decode_token_async,
        revoke_token_async,
    )

    token = create_access_token({"sub": "user@test.com"})

    await revoke_token_async(token)
    result = await decode_token_async(token)

    assert result is None, (
        "Revoked token must be rejected even with Redis removed — "
        "in-memory fallback is the contract."
    )


def test_memory_revocation_store_round_trips():
    """Direct check on the memory revocation primitive."""
    from app.core.security import _is_revoked_memory, _revoke_memory

    jti = "test-jti-mem-roundtrip"
    assert _is_revoked_memory(jti) is False
    _revoke_memory(jti, ttl_seconds=60)
    assert _is_revoked_memory(jti) is True


# ─────────────────────── access service no-op ────────────────────────


@pytest.mark.asyncio
async def test_access_service_invalidate_is_noop_without_redis(db):
    """``AccessService.invalidate_access_cache`` must not blow up when
    the Redis client is the no-op stub. The cache invalidation
    silently degrades — which is correct: there's nothing to
    invalidate when there's no shared cache."""
    from app.services.access_service import AccessService

    svc = AccessService(db)
    # Should not raise.
    await svc.invalidate_access_cache(user_id=999)
