"""Per-tenant rate limit dependency tests.

The legacy enforcers (``enforce_ai_rate_limit`` / ``enforce_upload_rate_limit``)
key by user id. V12+ adds a tenant-level cap on top so a single
tenant can't exhaust the instance budget by rotating through users.

These tests validate the dependency in isolation:
- Tenant key ``tenant:N`` is used when ``current_user.tenant_id`` is set.
- Single-tenant users (``tenant_id=None``) bypass the tenant cap.
- 429 raised at the documented threshold.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core import rate_limit


@dataclass
class _FakeUser:
    id: int
    tenant_id: int | None


@dataclass
class _FakeRequest:
    headers: dict
    client: object | None = None


@pytest.mark.asyncio
async def test_tenant_rate_limit_noop_for_legacy_user(monkeypatch):
    """``tenant_id=None`` users must bypass the tenant bucket entirely."""
    bucket = defaultdict(deque)
    dep = rate_limit.make_tenant_rate_limit(
        bucket, "RATE_LIMIT_TENANT_AI", "limit"
    )
    user = _FakeUser(id=1, tenant_id=None)
    # Should never raise even after many invocations.
    for _ in range(100):
        await dep(_FakeRequest(headers={}), current_user=user)
    assert len(bucket) == 0  # no key written


@pytest.mark.asyncio
async def test_tenant_rate_limit_blocks_when_over_threshold(monkeypatch):
    """Tenant bucket fills up and 429s once the per-window count exceeds
    the rate limit. Uses a tiny rate to keep the test fast."""
    monkeypatch.setattr(
        rate_limit.settings, "RATE_LIMIT_TENANT_AI", "3/minute"
    )
    bucket = defaultdict(deque)
    dep = rate_limit.make_tenant_rate_limit(
        bucket, "RATE_LIMIT_TENANT_AI", "limit"
    )
    user = _FakeUser(id=1, tenant_id=42)

    # First 3 pass.
    for _ in range(3):
        await dep(_FakeRequest(headers={}), current_user=user)

    # 4th raises.
    with pytest.raises(HTTPException) as exc:
        await dep(_FakeRequest(headers={}), current_user=user)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_tenant_rate_limit_isolated_per_tenant(monkeypatch):
    """Tenant A hitting the cap must not affect tenant B."""
    monkeypatch.setattr(
        rate_limit.settings, "RATE_LIMIT_TENANT_AI", "2/minute"
    )
    bucket = defaultdict(deque)
    dep = rate_limit.make_tenant_rate_limit(
        bucket, "RATE_LIMIT_TENANT_AI", "limit"
    )
    user_a = _FakeUser(id=1, tenant_id=1)
    user_b = _FakeUser(id=2, tenant_id=2)

    # Tenant 1 fills its bucket
    await dep(_FakeRequest(headers={}), current_user=user_a)
    await dep(_FakeRequest(headers={}), current_user=user_a)
    with pytest.raises(HTTPException):
        await dep(_FakeRequest(headers={}), current_user=user_a)

    # Tenant 2 still has full budget
    await dep(_FakeRequest(headers={}), current_user=user_b)
    await dep(_FakeRequest(headers={}), current_user=user_b)


@pytest.mark.asyncio
async def test_tenant_rate_limit_handles_none_user(monkeypatch):
    """Anonymous request (no current_user) is treated as no tenant
    and skips the tenant bucket — per-IP enforcement still applies
    via the per-user enforcer wrapping pattern in production."""
    bucket = defaultdict(deque)
    dep = rate_limit.make_tenant_rate_limit(
        bucket, "RATE_LIMIT_TENANT_AI", "limit"
    )
    # current_user=None
    await dep(_FakeRequest(headers={}), current_user=None)
    assert len(bucket) == 0
