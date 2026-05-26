"""F-005 — one-shot nonce for destructive admin actions.

Used by the merge endpoint (and any future hard-delete / KVKK
finalise / bulk-revoke). Prevents:

  * Accidental double-click double-execution (network retry).
  * Replay of a captured POST against the same operator's session.

Flow:

    1. Frontend opens the destructive form (e.g. merge preview).
       It calls ``POST /admin/nonces`` to obtain a fresh nonce.
    2. The nonce is bound to the current user, the action_type, and
       a 5-min TTL.
    3. The final POST (e.g. ``POST /admin/merge``) includes the
       nonce. Backend calls :func:`consume_nonce` — if the row's
       ``consumed_at`` is already set, the request is rejected.

This is *idempotency-key style*, not CSRF (CSRF is handled by the
existing X-CSRF-Token header). The two are complementary.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


NONCE_TTL_MINUTES = 5


class NonceInvalid(Exception):
    """Raised when the nonce is missing, expired, consumed, or
    bound to a different user / action."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def issue_nonce(
    db: AsyncSession,
    *,
    user_id: int,
    action_type: str,
) -> str:
    """Mint and persist a fresh nonce. Returns the plaintext nonce."""
    nonce = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(minutes=NONCE_TTL_MINUTES)
    await db.execute(
        text(
            """
            INSERT INTO admin_action_nonces
              (nonce, user_id, action_type, expires_at)
            VALUES
              (:nonce, :uid, :action, :exp)
            """
        ),
        {
            "nonce": nonce,
            "uid": user_id,
            "action": action_type,
            "exp": expires,
        },
    )
    await db.flush()
    return nonce


async def consume_nonce(
    db: AsyncSession,
    *,
    nonce: str,
    user_id: int,
    action_type: str,
) -> None:
    """Validate + atomically mark consumed.

    All-or-nothing: any of (missing, expired, wrong-user, wrong-action,
    already-consumed) → :class:`NonceInvalid`. Otherwise the row's
    ``consumed_at`` is stamped and the caller proceeds with the
    destructive action.

    Race-safe via the ``UPDATE ... WHERE consumed_at IS NULL`` clause —
    only one writer wins.
    """
    res = await db.execute(
        text(
            """
            UPDATE admin_action_nonces
               SET consumed_at = now()
             WHERE nonce       = :nonce
               AND user_id     = :uid
               AND action_type = :action
               AND consumed_at IS NULL
               AND expires_at  > now()
            RETURNING nonce
            """
        ),
        {"nonce": nonce, "uid": user_id, "action": action_type},
    )
    row = res.first()
    if row is None:
        # Disambiguate for the error message — best-effort lookup.
        existing = (
            await db.execute(
                text(
                    "SELECT user_id, action_type, consumed_at, expires_at "
                    "FROM admin_action_nonces WHERE nonce = :nonce"
                ),
                {"nonce": nonce},
            )
        ).first()
        if existing is None:
            raise NonceInvalid("not_found")
        if existing[2] is not None:
            raise NonceInvalid("already_consumed")
        if existing[3] is not None and existing[3].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise NonceInvalid("expired")
        if existing[0] != user_id:
            raise NonceInvalid("wrong_user")
        if existing[1] != action_type:
            raise NonceInvalid("wrong_action")
        raise NonceInvalid("unknown")
    await db.flush()


async def cleanup_expired_nonces(db: AsyncSession) -> int:
    """Cron: ``DELETE WHERE expires_at < now()``. Returns row count."""
    res = await db.execute(
        text("DELETE FROM admin_action_nonces WHERE expires_at < now()")
    )
    return int(res.rowcount or 0)
