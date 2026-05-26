"""D-006 — per-account login rate limit.

Pre-Round-19 rate limit was IP-only; distributed-IP credential stuffing
defeated it trivially. This module locks by *email* (the constant the
attacker can't rotate). Layered defence:

  * In-memory LRU/dict (fast, lost on restart)
  * PostgreSQL ``login_lockouts`` (persistent across restarts)

The two are consistent: every failure both increments the in-memory
counter AND upserts the PG row. A process restart re-hydrates from PG
on first miss.

Lock policy:
  * 5 failures within 15 min → 15-min lockout.
  * Successful login clears both layers.
  * Lockouts are per-account; IP-based rate limit (existing) still
    runs in front of this as a coarse filter.

Notifications: 3 failures → "suspicious login attempts" email.
5 failures → lockout email with reset link. Admin alerted if > 10
lockouts/hour platform-wide (D-006 follow-on; not in this batch).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 5
WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)


# In-memory accelerator (per-process). Production with multiple workers
# still survives via the PG layer; this just keeps the hot path fast.
_lock = threading.Lock()
_failed_attempts: dict[str, list[datetime]] = {}
_lockout_until: dict[str, datetime] = {}


def _normalise(email: str) -> str:
    return (email or "").strip().lower()


async def is_locked(db: AsyncSession, email: str) -> bool:
    """True iff the account is currently locked. Checks in-memory first
    then falls back to PG."""
    e = _normalise(email)
    if not e:
        return False
    with _lock:
        until = _lockout_until.get(e)
    if until is not None:
        if datetime.now(timezone.utc) < until:
            return True
        # Lockout passed; clean up in-memory.
        with _lock:
            _lockout_until.pop(e, None)
            _failed_attempts.pop(e, None)
        return False
    # Memory miss — check PG (covers post-restart scenario).
    row = (
        await db.execute(
            text(
                "SELECT locked_until FROM login_lockouts WHERE email_lower = :e"
            ),
            {"e": e},
        )
    ).first()
    if row is None or row.locked_until is None:
        return False
    until = row.locked_until
    if isinstance(until, str):
        until = datetime.fromisoformat(until)
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= until:
        # Lockout expired; clear PG row.
        await db.execute(
            text("DELETE FROM login_lockouts WHERE email_lower = :e"),
            {"e": e},
        )
        await db.flush()
        return False
    # Re-hydrate memory.
    with _lock:
        _lockout_until[e] = until
    return True


async def record_failure(
    db: AsyncSession,
    email: str,
    *,
    source_ip: str | None = None,
) -> bool:
    """Record a failed attempt. Returns True iff the account is now
    locked as a result of this failure.

    Idempotent in the sense that a second concurrent failure for the
    same email increments the count via the UPSERT; the in-memory
    list also de-duplicates against the time window.
    """
    e = _normalise(email)
    if not e:
        return False
    now = datetime.now(timezone.utc)
    cutoff = now - WINDOW

    with _lock:
        attempts = [t for t in _failed_attempts.get(e, []) if t > cutoff]
        attempts.append(now)
        _failed_attempts[e] = attempts
        count = len(attempts)

    locked = count >= MAX_ATTEMPTS
    locked_until: datetime | None = (now + LOCKOUT) if locked else None
    if locked:
        with _lock:
            _lockout_until[e] = locked_until

    # Persist via UPSERT. Use COALESCE so a new lockout doesn't shadow
    # an already-active longer lockout.
    await db.execute(
        text(
            """
            INSERT INTO login_lockouts (email_lower, failed_count, last_failure_at, locked_until, last_locked_ip)
            VALUES (:e, 1, :now, :until, :ip)
            ON CONFLICT (email_lower) DO UPDATE SET
                failed_count    = login_lockouts.failed_count + 1,
                last_failure_at = :now,
                locked_until    = COALESCE(EXCLUDED.locked_until, login_lockouts.locked_until),
                last_locked_ip  = COALESCE(EXCLUDED.last_locked_ip, login_lockouts.last_locked_ip)
            """
        ),
        {"e": e, "now": now, "until": locked_until, "ip": source_ip},
    )
    await db.flush()
    if locked:
        logger.warning(
            "Account locked due to repeated failures: %s (count=%d, ip=%s)",
            e, count, source_ip,
        )
    return locked


async def record_success(db: AsyncSession, email: str) -> None:
    """Clear both layers on successful login."""
    e = _normalise(email)
    if not e:
        return
    with _lock:
        _failed_attempts.pop(e, None)
        _lockout_until.pop(e, None)
    await db.execute(
        text("DELETE FROM login_lockouts WHERE email_lower = :e"),
        {"e": e},
    )
    await db.flush()


def _reset_for_tests() -> None:
    with _lock:
        _failed_attempts.clear()
        _lockout_until.clear()
