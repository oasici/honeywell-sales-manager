"""F-006 — e-Sign OTP flow.

Pre-Round-19 the e-Sign token was a single 30-day URL that anyone
who saw the email (forwards, screenshots, breached mailboxes) could
use to sign on the customer's behalf. The legal value of such a
signature is *zero* in most jurisdictions because there's no proof
of signer identity.

Post-Round-19 flow:

    1. Server issues a short token (url-safe random, 30 char).
       Stored hashed (sha256). 7-day expiry, single-use.

    2. Customer opens /sign/<token>. Page shows ONLY the masked
       recipient email + "Send OTP" button. Contract content is
       NOT visible yet.

    3. POST /sign/<token>/send-otp:
        - Server generates a 6-digit OTP, hashes it, stores hash.
        - Sends OTP via email to the *bound* recipient_email.
        - Rate-limited: max 3 sends per token per 24h.

    4. POST /sign/<token>/verify-otp with the code:
        - 5 wrong attempts → token invalidated.
        - Correct → contract content unlocked.

    5. POST /sign/<token>/sign with signature payload:
        - Records signed_at, ip_used, ua_used.
        - Token marked consumed.

This module is the data layer + the verification logic. The HTTP
endpoints (separate FE work) call these helpers; the helpers stay
testable without a request context.

Why email-only OTP and not SMS:
    - The customer's contact channel is already their email (the
      sign invite went there).
    - SMS adds Twilio dependency, MSISDN data collection, and
      another compliance scope.
    - At 20-30 users this isn't worth the cost. Upgrade to SMS for
      contracts >100K TRY when first enterprise customer demands it.

Security notes:
    - OTP is hashed at rest; even with a DB dump the codes can't be
      replayed.
    - Token + OTP are independent secrets — leaking one without
      the other is useless.
    - Recipient binding (recipient_email) is fixed at token issue;
      changing it = new token.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Tuneable from settings later. Defaults chosen for "small team" UX.
TOKEN_TTL_DAYS = 7
MAX_OTP_SENDS_PER_TOKEN = 3
MAX_OTP_ATTEMPTS = 5
OTP_VALID_MINUTES = 10


class SignTokenError(Exception):
    """Raised on any invalid-state condition during the sign flow.

    The HTTP layer maps to specific status codes:
        * ``expired``        → 410 Gone
        * ``consumed``       → 410 Gone
        * ``otp_rate``       → 429 Too Many Requests
        * ``otp_locked``     → 423 Locked (5 wrong tries → kill token)
        * ``otp_wrong``      → 400 Bad Request
        * ``otp_unverified`` → 403 Forbidden (sign before OTP)
    """

    def __init__(self, reason: str, detail: str | None = None):
        self.reason = reason
        self.detail = detail
        super().__init__(detail or reason)


@dataclass(frozen=True)
class IssuedToken:
    """Returned to the email-sender path. The *plaintext* token is
    only ever held in memory long enough to embed in the email body —
    we store the hash."""

    plaintext: str
    expires_at: datetime


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_otp() -> str:
    """Return a 6-digit numeric code (zero-padded).

    Numeric on purpose: lower friction for customers typing on phones
    where the keypad context switches to numeric. Six digits = ~1M
    combinations; combined with the 5-attempt lockout that's a
    brute-force margin of 200,000:1.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


async def issue_token(
    db: AsyncSession,
    *,
    contract_id: int,
    tenant_id: int,
    recipient_email: str,
) -> IssuedToken:
    """Create a fresh sign token row. Returns the plaintext token
    to be emailed; only the hash is stored.

    Caller composes the URL ``/sign/<plaintext>`` and emails it.
    """
    plain = secrets.token_urlsafe(24)   # 32 base64url chars
    token_hash = _hash(plain)
    expires = _now() + timedelta(days=TOKEN_TTL_DAYS)

    await db.execute(
        text(
            """
            INSERT INTO sign_otp_tokens
              (contract_id, tenant_id, token_hash, recipient_email, expires_at)
            VALUES
              (:cid, :tid, :hash, :email, :exp)
            """
        ),
        {
            "cid": contract_id,
            "tid": tenant_id,
            "hash": token_hash,
            "email": recipient_email.lower().strip(),
            "exp": expires,
        },
    )
    await db.flush()
    return IssuedToken(plaintext=plain, expires_at=expires)


async def _fetch_token_row(db: AsyncSession, plaintext: str) -> dict:
    """Look up token by hash. Raises if missing/expired/consumed."""
    row = (
        await db.execute(
            text(
                """
                SELECT id, contract_id, tenant_id, recipient_email,
                       otp_hash, otp_sent_at, otp_send_count,
                       otp_attempts, otp_verified_at, signed_at,
                       expires_at
                FROM sign_otp_tokens
                WHERE token_hash = :hash
                """
            ),
            {"hash": _hash(plaintext)},
        )
    ).first()
    if row is None:
        raise SignTokenError("not_found")
    data = dict(row._mapping)
    if _now() > data["expires_at"].replace(tzinfo=timezone.utc):
        raise SignTokenError("expired")
    if data.get("signed_at") is not None:
        raise SignTokenError("consumed")
    return data


async def get_recipient_summary(
    db: AsyncSession, plaintext: str
) -> dict:
    """Token-lookup endpoint result. Returns masked recipient only —
    nothing about the contract content."""
    row = await _fetch_token_row(db, plaintext)
    email = row["recipient_email"]
    return {
        "masked_email": _mask_email(email),
        "expires_at": row["expires_at"],
        "otp_sent": row.get("otp_sent_at") is not None,
        "otp_verified": row.get("otp_verified_at") is not None,
    }


def _mask_email(email: str) -> str:
    """``ahmet@acme.com`` → ``a***@acme.com``."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


async def send_otp(
    db: AsyncSession,
    plaintext: str,
    *,
    send_email: callable,
) -> str:
    """Generate a new OTP, persist its hash, deliver via ``send_email``.

    ``send_email(to, subject, body) -> None`` is dependency-injected
    so unit tests don't have to wire a real SMTP. Returns the masked
    recipient for the UI banner.
    """
    row = await _fetch_token_row(db, plaintext)
    if row["otp_send_count"] >= MAX_OTP_SENDS_PER_TOKEN:
        raise SignTokenError("otp_rate", "Daily OTP send limit reached")

    code = _gen_otp()
    otp_hash = _hash(code)
    await db.execute(
        text(
            """
            UPDATE sign_otp_tokens
               SET otp_hash       = :h,
                   otp_sent_at    = now(),
                   otp_send_count = otp_send_count + 1,
                   otp_attempts   = 0
             WHERE id = :id
            """
        ),
        {"h": otp_hash, "id": row["id"]},
    )
    await db.flush()

    # Fire the email. Caller's send_email handles SMTP errors.
    send_email(
        row["recipient_email"],
        "Elektronik imza doğrulama kodu",
        f"Sözleşme imza doğrulama kodunuz: {code}\n\n"
        f"Bu kod {OTP_VALID_MINUTES} dakika boyunca geçerlidir.",
    )
    return _mask_email(row["recipient_email"])


async def verify_otp(
    db: AsyncSession, plaintext: str, code: str
) -> None:
    """Mark the token's OTP verified iff ``code`` matches.

    Wrong attempts increment ``otp_attempts``; after MAX_OTP_ATTEMPTS
    the token is invalidated (expires_at set to now()).
    """
    row = await _fetch_token_row(db, plaintext)
    if not row.get("otp_hash") or not row.get("otp_sent_at"):
        raise SignTokenError("otp_unverified", "OTP not sent yet")

    # OTP age check
    sent_at = row["otp_sent_at"].replace(tzinfo=timezone.utc)
    if _now() > sent_at + timedelta(minutes=OTP_VALID_MINUTES):
        raise SignTokenError("otp_expired", "Code expired; request a new one")

    if row["otp_attempts"] >= MAX_OTP_ATTEMPTS:
        raise SignTokenError("otp_locked", "Token invalidated")

    if _hash(code) != row["otp_hash"]:
        new_attempts = row["otp_attempts"] + 1
        if new_attempts >= MAX_OTP_ATTEMPTS:
            await db.execute(
                text(
                    "UPDATE sign_otp_tokens SET otp_attempts = :n, expires_at = now() "
                    "WHERE id = :id"
                ),
                {"n": new_attempts, "id": row["id"]},
            )
            await db.flush()
            raise SignTokenError("otp_locked", "Too many wrong attempts")
        await db.execute(
            text(
                "UPDATE sign_otp_tokens SET otp_attempts = :n WHERE id = :id"
            ),
            {"n": new_attempts, "id": row["id"]},
        )
        await db.flush()
        raise SignTokenError("otp_wrong", "Invalid code")

    await db.execute(
        text(
            "UPDATE sign_otp_tokens SET otp_verified_at = now() WHERE id = :id"
        ),
        {"id": row["id"]},
    )
    await db.flush()


async def consume_for_signing(
    db: AsyncSession,
    plaintext: str,
    *,
    ip: str | None,
    ua: str | None,
) -> int:
    """Mark the token consumed. Returns ``contract_id`` so the
    caller can stamp the signature on the contract row.

    Refuses when OTP wasn't verified (the verify step is mandatory).
    """
    row = await _fetch_token_row(db, plaintext)
    if row.get("otp_verified_at") is None:
        raise SignTokenError("otp_unverified", "OTP must be verified first")
    await db.execute(
        text(
            """
            UPDATE sign_otp_tokens
               SET signed_at = now(),
                   ip_used   = :ip,
                   ua_used   = :ua
             WHERE id = :id
            """
        ),
        {"ip": ip, "ua": ua, "id": row["id"]},
    )
    await db.flush()
    return int(row["contract_id"])
