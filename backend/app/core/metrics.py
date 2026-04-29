"""Prometheus metrics (production hardening)."""

from __future__ import annotations

import time
from typing import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

http_requests_total = Counter(
    "hsm_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "hsm_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# V13 security signal: every blocked cross-tenant access bumps this
# counter. A single user spiking here = ID enumeration probe;
# wire an alert in Grafana / Sentry on
# ``rate(hsm_cross_tenant_blocked_total[5m]) > N``.
cross_tenant_blocked_total = Counter(
    "hsm_cross_tenant_blocked_total",
    "Cross-tenant access attempts blocked by assert_same_tenant",
    ["user_id", "target_tenant"],
)


def _safe_path(path: str) -> str:
    # Reduce cardinality: collapse numeric IDs into :id.
    parts = []
    for p in (path or "").split("/"):
        if p.isdigit():
            parts.append(":id")
        else:
            parts.append(p)
    return "/".join(parts) or "/"


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = _safe_path(request.url.path)
        start = time.perf_counter()
        status = "500"
        try:
            resp = await call_next(request)
            status = str(resp.status_code)
            return resp
        finally:
            dt = time.perf_counter() - start
            http_requests_total.labels(method=method, path=path, status=status).inc()
            http_request_duration_seconds.labels(method=method, path=path).observe(dt)


def metrics_response() -> Response:
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

