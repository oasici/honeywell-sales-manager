"""F-024 — mandatory unsubscribe + consent tracking for email sequences.

KVKK (Article 5/2-h) and CAN-SPAM both require:

  1. Every commercial email include a clear, one-click unsubscribe.
  2. Opt-out is honored permanently from the moment it's recorded.
  3. The original consent source is auditable.

Pre-Round-19 sequence templates could be sent without an
unsubscribe token. This module enforces:

  * ``validate_sequence_body`` — template must contain
    ``{{unsubscribe_link}}``. Saving without it raises.
  * ``issue_unsubscribe_token`` — per-recipient-per-sequence token,
    embedded in the email link.
  * ``mark_opted_out`` — recorded immutably in ``email_optouts``.
  * ``is_opted_out`` — checked before every send; opt-out recipients
    are skipped silently with an audit-log entry.

Tokens are hashed at rest — even a DB dump can't be replayed to
spoof an unsubscribe (which would be a weird attack but the
principle is consistent with sign_otp).
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_UNSUBSCRIBE_TOKEN_RE = re.compile(
    r"\{\{\s*unsubscribe_link\s*\}\}", re.IGNORECASE
)
# D-024 — placement check: forbid the token inside an HTML comment.
# A clever sequence author could embed ``{{unsubscribe_link}}`` in
# ``<!-- ... -->`` which would parse-pass the validator but never
# render. The opt-out link must be visible to the recipient.
_TOKEN_IN_COMMENT_RE = re.compile(
    r"<!--[^-]*(?:-(?!-)[^-]*)*?\{\{\s*unsubscribe_link\s*\}\}",
    re.IGNORECASE | re.DOTALL,
)


class SequenceValidationError(Exception):
    """Raised when a sequence template can't be saved."""


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def validate_sequence_body(body: str) -> None:
    """Raise if ``{{unsubscribe_link}}`` is missing.

    Sequences without unsubscribe = KVKK + CAN-SPAM violation. The
    editor calls this *before* save; the API path calls it again
    server-side so a hand-crafted POST can't bypass the FE check.
    """
    if not body or not body.strip():
        raise SequenceValidationError("sequence_body_empty")
    if not _UNSUBSCRIBE_TOKEN_RE.search(body):
        raise SequenceValidationError(
            "sequence_body_missing_unsubscribe_token"
        )
    # D-024 — the visible-placement check. Token inside an HTML
    # comment doesn't render to the recipient → KVKK/CAN-SPAM fail.
    if _TOKEN_IN_COMMENT_RE.search(body):
        raise SequenceValidationError(
            "sequence_body_unsubscribe_in_comment"
        )


@dataclass(frozen=True)
class IssuedOptOutToken:
    plaintext: str          # the URL component
    token_hash: str         # what we store


def issue_unsubscribe_token() -> IssuedOptOutToken:
    """Mint a fresh opt-out token for one recipient-sequence pair."""
    plain = secrets.token_urlsafe(24)
    return IssuedOptOutToken(plaintext=plain, token_hash=_hash(plain))


async def mark_opted_out(
    db: AsyncSession,
    *,
    tenant_id: int,
    email: str,
    source: str = "unsubscribe_link",
    sequence_id: int | None = None,
    unsubscribe_token: str | None = None,
) -> None:
    """Record an opt-out. Idempotent — a second click on the same
    link is a no-op (the UNIQUE constraint catches it).

    ``unsubscribe_token`` should be the *hash*, not the plaintext.
    """
    email_n = email.lower().strip()
    try:
        await db.execute(
            text(
                """
                INSERT INTO email_optouts
                  (tenant_id, email, source, sequence_id, unsubscribe_token)
                VALUES
                  (:tid, :email, :source, :seq, :token)
                ON CONFLICT (tenant_id, email, sequence_id) DO NOTHING
                """
            ),
            {
                "tid": tenant_id,
                "email": email_n,
                "source": source,
                "seq": sequence_id,
                "token": unsubscribe_token,
            },
        )
        await db.flush()
    except Exception:
        await db.rollback()
        # Re-raise — caller decides what to do (probably 500).
        raise
    logger.info(
        "Opt-out recorded tenant=%d email=%s source=%s sequence=%s",
        tenant_id, email_n, source, sequence_id,
    )


async def is_opted_out(
    db: AsyncSession,
    *,
    tenant_id: int,
    email: str,
    sequence_id: int | None = None,
) -> bool:
    """Block-pre-send check.

    A row with ``sequence_id IS NULL`` is a *global* opt-out — applies
    to every sequence. A row with a specific sequence_id only blocks
    that sequence.
    """
    email_n = email.lower().strip()
    row = (
        await db.execute(
            text(
                """
                SELECT 1 FROM email_optouts
                WHERE tenant_id = :tid
                  AND email = :email
                  AND (sequence_id IS NULL OR sequence_id = :seq)
                LIMIT 1
                """
            ),
            {"tid": tenant_id, "email": email_n, "seq": sequence_id},
        )
    ).first()
    return row is not None


def render_unsubscribe_link(
    *,
    base_url: str,
    token: str,
) -> str:
    """Build the customer-facing URL embedded in the email body.

    Pure function — caller can use it from any template engine. The
    URL must be HTTPS in prod; we don't enforce that here (let the
    caller set base_url correctly via config).
    """
    return f"{base_url.rstrip('/')}/unsubscribe/{token}"
