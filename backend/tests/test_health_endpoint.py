"""Health endpoint tests — verifies the /api/health contract.

The endpoint is the single integration point for UptimeRobot, BetterStack,
and Render's deploy gating. Schema changes here have downstream consequences,
so the contract is locked in tests.
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from app.core.circuit_breaker import (
    claude_breaker,
    currency_breaker,
    graph_breaker,
    qdrant_breaker,
)


@pytest.fixture(autouse=True)
def _reset_all_breakers():
    """Each test starts with all breakers closed; clean up after to avoid bleed."""
    for cb in (claude_breaker, graph_breaker, currency_breaker, qdrant_breaker):
        cb.reset()
    yield
    for cb in (claude_breaker, graph_breaker, currency_breaker, qdrant_breaker):
        cb.reset()


@pytest.mark.asyncio
async def test_health_endpoint_returns_circuits_block(client: AsyncClient):
    """All four breaker states are exposed under `circuits`."""
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()

    assert "circuits" in body
    circuits = body["circuits"]
    for name in ("claude_api", "graph_api", "currency_api", "qdrant"):
        assert name in circuits, f"missing breaker '{name}' in /api/health"
        assert circuits[name]["state"] == "closed"
        assert circuits[name]["failure_count"] == 0


@pytest.mark.asyncio
async def test_health_status_degrades_when_breaker_open(client: AsyncClient):
    """When any breaker is open, top-level status flips to 'degraded'."""
    # Force claude_breaker into open state
    claude_breaker._state = "open"
    claude_breaker._failure_count = 5
    claude_breaker._last_failure_time = time.time()  # within recovery window

    r = await client.get("/api/health")
    body = r.json()

    assert body["status"] == "degraded"
    assert body["circuits"]["claude_api"]["state"] == "open"
    assert body["circuits"]["claude_api"]["failure_count"] == 5
    # Other breakers still closed
    assert body["circuits"]["graph_api"]["state"] == "closed"


@pytest.mark.asyncio
async def test_health_status_healthy_when_all_breakers_closed(client: AsyncClient):
    """All breakers closed + DB ok = 'healthy'."""
    r = await client.get("/api/health")
    body = r.json()

    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "ok"
    assert all(
        c["state"] == "closed"
        for c in body["circuits"].values()
        if isinstance(c, dict)
    )


@pytest.mark.asyncio
async def test_health_response_includes_uptime_and_version(client: AsyncClient):
    """Response shape is stable: status, checks, circuits, version, uptime_seconds."""
    r = await client.get("/api/health")
    body = r.json()

    assert set(body.keys()) >= {"status", "checks", "circuits", "version", "uptime_seconds"}
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0
    assert body["version"] == "2.0.0"
