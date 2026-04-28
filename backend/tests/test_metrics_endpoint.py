"""Smoke tests for the /metrics Prometheus endpoint.

Catches regressions in three places that can quietly break observability:
- /metrics endpoint disappearing (route registration)
- Prometheus content-type drift (scraper config breaks)
- Counter wiring lost (no labels emitted → Grafana dashboards go flat)

These tests don't measure values — observability is about *shape*, not
specific counts. We exercise the endpoint, verify the metric names we
care about appear in the output, and trust the scraper for the rest.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client: AsyncClient):
    r = await client.get("/metrics")
    assert r.status_code == 200
    # Prometheus exposition format uses ``text/plain`` with explicit version.
    ctype = r.headers["content-type"]
    assert "text/plain" in ctype
    body = r.text
    # # HELP / # TYPE comments must be present for valid Prom format.
    assert "# HELP" in body
    assert "# TYPE" in body


@pytest.mark.asyncio
async def test_metrics_includes_app_counters(client: AsyncClient):
    """The ``hsm_*`` counters/histograms we instrumented must appear.

    If a future refactor drops PrometheusMiddleware or renames a
    metric, this test catches it before Grafana dashboards go silent.
    """
    # Trigger at least one request so the counter has a label set.
    await client.get("/api/health")
    r = await client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "hsm_http_requests_total" in body
    assert "hsm_http_request_duration_seconds" in body


@pytest.mark.asyncio
async def test_metrics_path_label_normalises_numeric_ids(client: AsyncClient):
    """``/customers/123`` must be exported as ``/customers/:id`` — otherwise
    every request creates a new label set and Prometheus cardinality blows up.
    """
    # Hit a path that contains a numeric ID. We don't care about the
    # response status — only the label normalisation.
    await client.get("/api/v1/customers/9999")
    r = await client.get("/metrics")
    body = r.text
    # The exact label text varies by status, but ``:id`` should appear
    # somewhere on a labelled line.
    assert "/:id" in body or ":id" in body
