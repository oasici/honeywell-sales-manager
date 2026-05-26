"""D-010 — cross-tenant probe detection.

F-020 closes the timing-channel hole (constant-time 404). This module
adds the *visibility* layer: every blocked cross-tenant access is
recorded so security can detect ID-enumeration attempts.

Hooked into ``app.services.tenant_context.load_with_tenant_check`` —
when the single-query tenant filter returns no row, we don't know
whether the row truly doesn't exist or belongs to another tenant.
Solution: a *separate* lookup (no tenant filter) tells us the truth,
but we run it **only after** the 404 response is shaped, so latency
doesn't leak. The check is fire-and-forget; the user's response is
already on the wire.

Alerting (D-010 follow-on):
  * > 10 attempts/hour from one user → ops on-call paged
  * Daily report of top probing users
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_TABLE_BY_ENTITY = {
    "customer":     "customers",
    "lead":         "leads",
    "opportunity":  "opportunities",
    "quote":        "quotes",
    "contract":     "contracts",
    "invoice":      "invoices",
    "email":        "email_requests",
}


async def maybe_record_probe(
    db: AsyncSession,
    *,
    user_id: int,
    user_tenant: int,
    entity: str,
    entity_id: int,
    ip: str | None = None,
    ua: str | None = None,
) -> None:
    """If ``entity_id`` exists for a DIFFERENT tenant, log the probe.

    Cheap: a single SELECT + (optional) INSERT. Idempotent — the same
    probe within seconds appears as multiple rows (intentional;
    velocity is the signal we want).

    Silent on errors — never let observability instrumentation break
    the user request path.
    """
    table = _TABLE_BY_ENTITY.get(entity.lower())
    if table is None:
        return
    try:
        row = (
            await db.execute(
                text(
                    f"SELECT tenant_id FROM {table} WHERE id = :id LIMIT 1"
                ),
                {"id": entity_id},
            )
        ).first()
        if row is None:
            # Genuinely missing — not a probe.
            return
        if row.tenant_id == user_tenant:
            # Same-tenant 404 caused by something else (deleted_at,
            # permission filter at endpoint, …). Not a probe.
            return
        # Foreign tenant — record the attempt.
        await db.execute(
            text(
                """
                INSERT INTO cross_tenant_attempts
                  (user_id, user_tenant, attempted_entity, attempted_id, ip, ua)
                VALUES (:uid, :tid, :ent, :eid, :ip, :ua)
                """
            ),
            {
                "uid": user_id, "tid": user_tenant,
                "ent": entity, "eid": entity_id,
                "ip": ip, "ua": (ua or "")[:1000],
            },
        )
        await db.flush()
        logger.warning(
            "Cross-tenant probe: user=%d tenant=%d entity=%s id=%d",
            user_id, user_tenant, entity, entity_id,
        )
    except Exception as exc:  # noqa: BLE001
        # Observability must never break the request path.
        logger.debug("Probe detection skipped (non-fatal): %s", exc)


async def count_recent_probes(
    db: AsyncSession,
    *,
    user_id: int,
    window_minutes: int = 60,
) -> int:
    """For the on-call dashboard. > 10 in 1h triggers a page."""
    row = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) FROM cross_tenant_attempts
                WHERE user_id = :uid
                  AND attempted_at >= now() - (:m || ' minutes')::interval
                """
            ),
            {"uid": user_id, "m": str(window_minutes)},
        )
    ).first()
    return int(row[0]) if row else 0
