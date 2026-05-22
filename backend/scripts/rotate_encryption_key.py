"""Round-18 Fernet key rotation script.

Re-encrypts every Fernet ciphertext stored in the database onto the
current primary ``ENCRYPTION_KEY``. After this runs cleanly the
operator can drop the old key from ``ENCRYPTION_KEY_OLD`` because
no row depends on it anymore.

Tables touched:

  * ``settings.value`` — the integration credentials table holds the
    IMAP password, the calendar OAuth token, the e-sign provider
    secret, etc.
  * ``email_credentials.password_encrypted`` — per-user SMTP / IMAP
    creds (round-9 e-mail-inbox feature).

The script is **idempotent**: each row is decrypted (succeeding
under either the primary or any old key), then re-encrypted with
the primary. Rows already on the primary key produce a fresh
ciphertext with a current timestamp but the plaintext is preserved.

Usage (operations runbook):

    1. Set the new key as primary, keep the previous one as old:
       export ENCRYPTION_KEY="<new>"
       export ENCRYPTION_KEY_OLD="<previous>"
    2. Deploy. New writes go on the new key; old reads still work.
    3. Run this script against prod:
       python -m scripts.rotate_encryption_key --apply
    4. Drop ENCRYPTION_KEY_OLD from env on the next deploy.

Dry-run (default) prints the rows that would be touched without
making any database changes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow running directly from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import rotate_ciphertext
from app.core.database import async_session_maker


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


async def _rotate_settings_table(db: AsyncSession, *, apply: bool) -> int:
    """Re-encrypt every ``settings.value`` that looks like a Fernet
    ciphertext."""
    from app.models.setting import Setting

    rows = (await db.execute(select(Setting))).scalars().all()
    rotated = 0
    for row in rows:
        if not row.value:
            continue
        # Heuristic: Fernet ciphertext is URL-safe base64 starting
        # with the version byte (``gAA``). Pre-encryption legacy
        # plaintext doesn't have that prefix and is skipped.
        if not row.value.startswith("gAA"):
            continue
        try:
            new = rotate_ciphertext(row.value)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "settings[%s]: rotation failed (%s) — leaving as-is",
                row.key,
                exc,
            )
            continue
        if apply:
            row.value = new
        rotated += 1
        logger.info("settings[%s]: rotated", row.key)
    if apply:
        await db.commit()
    return rotated


async def _rotate_email_credentials(db: AsyncSession, *, apply: bool) -> int:
    """Re-encrypt every ``email_credentials.password_encrypted``."""
    try:
        from app.models.email_credential import EmailCredential
    except ImportError:
        logger.info("email_credentials table not present; skipping")
        return 0

    rows = (await db.execute(select(EmailCredential))).scalars().all()
    rotated = 0
    for row in rows:
        cipher = getattr(row, "password_encrypted", None)
        if not cipher or not cipher.startswith("gAA"):
            continue
        try:
            new = rotate_ciphertext(cipher)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "email_credentials[%d]: rotation failed (%s)",
                row.id,
                exc,
            )
            continue
        if apply:
            row.password_encrypted = new
        rotated += 1
        logger.info("email_credentials[%d]: rotated", row.id)
    if apply:
        await db.commit()
    return rotated


async def main(apply: bool) -> None:
    async with async_session_maker() as db:
        total = 0
        total += await _rotate_settings_table(db, apply=apply)
        total += await _rotate_email_credentials(db, apply=apply)
    mode = "applied" if apply else "would rotate (dry-run)"
    logger.info("Rotation summary — %s %d ciphertext(s)", mode, total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default: dry-run prints what would change)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.apply))
