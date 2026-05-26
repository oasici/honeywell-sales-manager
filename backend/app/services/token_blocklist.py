"""F-013 — persistent JWT JTI blocklist backed by PostgreSQL.

The existing two-layer revocation in ``app/core/security.py`` covers:

  * In-memory LRU (fast, per-process, lost on restart)
  * Redis (fast, multi-process, lost when Redis is wiped)

This module adds a third, durable layer: ``token_blocklist`` in
PostgreSQL. Revocation always writes here so a process restart never
"unrevokes" a logged-out session. Decode falls back to PG only when
both memory and Redis miss — kept slow on purpose because we want
the hot path to stay sub-millisecond.

A nightly cron (``cleanup_expired_blocklist``) drops rows with
``exp < now()`` so the table never grows past the active session
window × revoke rate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def revoke_jti_persistent(
    db: AsyncSession,
    *,
    jti: str,
    exp_ts: int,
    user_id: Optional[int] = None,
    reason: str = "logout",
) -> None:
    """Insert a JTI into the persistent blocklist.

    Idempotent: an already-revoked jti just bumps ``revoked_at``.
    Safe to call before or after the memory/Redis writes — order
    doesn't matter because all three are ORs.
    """
    exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO token_blocklist (jti, user_id, exp, revoked_at, reason)
            VALUES (:jti, :user_id, :exp, now(), :reason)
            ON CONFLICT (jti) DO UPDATE SET
                revoked_at = now(),
                reason     = EXCLUDED.reason
            """
        ),
        {"jti": jti, "user_id": user_id, "exp": exp_dt, "reason": reason},
    )
    await db.flush()


async def is_jti_revoked_persistent(db: AsyncSession, jti: str) -> bool:
    """Return True iff ``jti`` is in the persistent blocklist AND not yet expired.

    Rows past ``exp`` are treated as "no longer relevant" — the JWT
    is already invalid via its own ``exp`` claim, so the blocklist
    can drop it safely.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT 1 FROM token_blocklist
                WHERE jti = :jti AND exp > now()
                """
            ),
            {"jti": jti},
        )
    ).first()
    return row is not None


async def revoke_all_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    active_jtis: list[tuple[str, int]],
    reason: str = "logout_all",
) -> int:
    """Revoke every supplied JTI for a user (logout-everywhere).

    Caller supplies the list of (jti, exp_ts) pairs — typically read
    from a ``user_sessions`` table or computed from refresh tokens.
    Returns the number of new revocations.
    """
    if not active_jtis:
        return 0
    inserted = 0
    for jti, exp_ts in active_jtis:
        await revoke_jti_persistent(
            db, jti=jti, exp_ts=exp_ts, user_id=user_id, reason=reason
        )
        inserted += 1
    return inserted


async def cleanup_expired_blocklist(db: AsyncSession) -> int:
    """Cron entry-point. DELETE WHERE exp < now(). Returns deleted count.

    Idempotent. Safe to run hourly on small deployments, daily on
    large ones. Wrap the call site in its own transaction.
    """
    result = await db.execute(
        text("DELETE FROM token_blocklist WHERE exp < now()")
    )
    deleted = result.rowcount or 0
    if deleted:
        logger.info("token_blocklist cleanup: removed %d expired rows", deleted)
    return int(deleted)
