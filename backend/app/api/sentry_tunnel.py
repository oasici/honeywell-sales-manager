"""Sentry tunnel endpoint — proxies browser events to Sentry ingest.

Why this exists:
- Corporate firewalls, Turkish ISPs, and some antivirus products reset
  direct HTTPS connections to *.sentry.io. Without a tunnel, we lose
  frontend error visibility for a meaningful slice of real users.
- Also bypasses ad blockers that match Sentry's ingest hostnames.

Security notes:
- Only project IDs in SENTRY_ALLOWED_PROJECT_IDS can be forwarded.
  Otherwise any attacker could make our backend spam arbitrary Sentry
  orgs (quota burn / DoS amplification).
- Rate-limited per IP (100/minute) — enough for noisy error storms,
  low enough to prevent abuse.
- Payload is streamed body-as-is; we only parse the first line to
  extract the DSN header.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import settings
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])

# Hard upper bound — Sentry envelopes are small. Refuse obvious junk.
_MAX_ENVELOPE_BYTES = 1_000_000  # 1 MiB

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Shared HTTP client with reasonable timeouts for Sentry ingest."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
            follow_redirects=False,
        )
    return _client


def _allowed_project_ids() -> set[str]:
    raw = (settings.SENTRY_ALLOWED_PROJECT_IDS or "").strip()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


@router.post("/sentry-tunnel")
@limiter.limit("100/minute")
async def sentry_tunnel(request: Request) -> Response:
    """Proxy a Sentry envelope from the browser to the real ingest endpoint."""
    if not _allowed_project_ids():
        raise HTTPException(status_code=404, detail="Not found")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty envelope")
    if len(body) > _MAX_ENVELOPE_BYTES:
        raise HTTPException(status_code=413, detail="Envelope too large")

    # Sentry envelope format:
    #   <header json>\n<item header>\n<item payload>\n...
    # Only the first line is meaningful for routing.
    first_newline = body.find(b"\n")
    if first_newline == -1:
        raise HTTPException(status_code=400, detail="Malformed envelope")

    try:
        header = json.loads(body[:first_newline].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid envelope header")

    dsn_str = header.get("dsn")
    if not dsn_str or not isinstance(dsn_str, str):
        raise HTTPException(status_code=400, detail="Missing DSN in envelope header")

    try:
        parsed = urlparse(dsn_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid DSN")

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid DSN")
    # Only permit official Sentry SaaS hostnames — stops exfil to attacker host.
    if not parsed.hostname.endswith(".sentry.io") and parsed.hostname != "sentry.io":
        raise HTTPException(status_code=400, detail="DSN host not allowed")

    project_id = parsed.path.strip("/").split("/")[0] if parsed.path else ""
    if not project_id or not project_id.isdigit():
        raise HTTPException(status_code=400, detail="Missing project id")

    if project_id not in _allowed_project_ids():
        # Don't leak whether the project exists — make it look like a 404.
        logger.warning("sentry_tunnel_rejected project_id=%s", project_id)
        raise HTTPException(status_code=404, detail="Not found")

    upstream = f"https://{parsed.hostname}/api/{project_id}/envelope/"

    try:
        resp = await _get_client().post(
            upstream,
            content=body,
            headers={
                "Content-Type": "application/x-sentry-envelope",
                # Sentry expects no auth header when DSN public key is in the envelope header.
            },
        )
    except httpx.TimeoutException:
        logger.warning("sentry_tunnel_timeout project_id=%s", project_id)
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except httpx.HTTPError as exc:
        logger.warning("sentry_tunnel_upstream_error project_id=%s err=%s", project_id, exc)
        raise HTTPException(status_code=502, detail="Upstream error")

    # Pass through status + body so the browser SDK can honour rate limit headers.
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
