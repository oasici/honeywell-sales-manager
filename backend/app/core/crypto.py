"""Symmetric encryption helpers (Fernet) for at-rest secrets.

Round-4 R4-PII-1 / R4-PII-2 lifted these helpers out of
``app/api/v1/settings.py`` so multiple services can share them without
circular imports — the calendar OAuth token store and the e-sign
provider config writer both need ``encrypt_str`` / ``decrypt_str``.

Key resolution (Round-18 rotation-aware):

- ``ENCRYPTION_KEY`` env var = the **primary** key. All new writes
  encrypt with this one.
- ``ENCRYPTION_KEY_OLD`` env var = comma-separated list of older
  keys kept around for decrypt-only use. New writes never use them.
  When the operator runs the rotation script (Round-18), old keys
  age out of this list once every row has been re-encrypted.
- In dev/test (no env vars), persist a generated key to
  ``data/.encryption_key`` so workers + restarts share it.

The two-tier (primary + decrypt-only) pattern uses Cryptography's
``MultiFernet``: ``encrypt`` always uses the first key, ``decrypt``
tries each key in order. This gives us a zero-downtime rotation
without "decrypt all and re-encrypt all" coordination.

The legacy ``_encrypt_password`` / ``_decrypt_password`` in
``settings.py`` continue to work via re-export.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger(__name__)

_KEY_FILE = os.path.join("data", ".encryption_key")


def _load_keys() -> list[str]:
    """Resolve the active key list, primary first.

    Returns at least one Fernet-formatted key. Falls back to disk
    persistence in dev/test as before.
    """
    from app.core.config import settings as cfg

    primary = os.environ.get("ENCRYPTION_KEY", "").strip()
    rotation = [
        k.strip()
        for k in os.environ.get("ENCRYPTION_KEY_OLD", "").split(",")
        if k.strip()
    ]

    if primary:
        return [primary, *rotation]

    if cfg.is_production:
        raise RuntimeError(
            "ENCRYPTION_KEY must be set in production. "
            "Generate one with: python -c \"from cryptography.fernet "
            "import Fernet; print(Fernet.generate_key().decode())\""
        )

    # Dev/test fallback — persist generated key on disk for the
    # cross-restart use case.
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE) as fh:
            primary = fh.read().strip()
    if not primary:
        primary = Fernet.generate_key().decode()
        os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
        with open(_KEY_FILE, "w") as fh:
            fh.write(primary)
    os.environ["ENCRYPTION_KEY"] = primary
    return [primary, *rotation]


def get_fernet() -> Fernet | MultiFernet:
    """Return a Fernet (or MultiFernet for rotation) keyed by config.

    Round-18 — rotation-aware: when ``ENCRYPTION_KEY_OLD`` is set,
    returns a ``MultiFernet`` that encrypts with the primary key
    but accepts ciphertexts produced by any older key. New writes
    always use the primary; old reads keep working until the
    rotation script re-encrypts every row, at which point ops can
    drop the old key from ``ENCRYPTION_KEY_OLD``.
    """
    keys = _load_keys()
    fernets = [
        Fernet(k.encode() if isinstance(k, str) else k)
        for k in keys
    ]
    if len(fernets) == 1:
        return fernets[0]
    return MultiFernet(fernets)


def rotate_ciphertext(ciphertext: str) -> str:
    """Decrypt with whichever key works, re-encrypt with the primary.

    Used by the rotation script to walk every encrypted row in the
    database and migrate it onto the new primary key. Idempotent:
    a ciphertext already encrypted with the primary key returns
    the equivalent of itself (timestamp may differ but the
    plaintext is preserved).
    """
    fernet = get_fernet()
    plain = fernet.decrypt(ciphertext.encode()).decode()
    return fernet.encrypt(plain.encode()).decode()


def encrypt_str(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Returns the Fernet ciphertext (URL-safe b64)."""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_str(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext back to UTF-8.

    Raises ``InvalidToken`` when the input was not produced by
    ``encrypt_str`` with the current key.
    """
    return get_fernet().decrypt(ciphertext.encode()).decode()


def encrypt_json(obj: Any) -> str:
    """Encrypt a JSON-serialisable object as a Fernet ciphertext."""
    return encrypt_str(json.dumps(obj, default=str))


def decrypt_str_or_legacy_plaintext(value: str) -> str | None:
    """Decrypt a Fernet ciphertext-or-plain-string back to UTF-8.

    Round-5 R5-PII-5 — paired with the encrypt-on-PUT path in
    ``settings.update_settings``. Handles the rollout window where
    rows already in DB are still plaintext; new writes are Fernet
    ciphertext. Returns ``None`` when the input is empty.
    """
    if value is None or value == "":
        return None
    try:
        return decrypt_str(value)
    except InvalidToken:
        # Legacy plaintext — pre-R5-PII-5 write site or a value that
        # never went through encrypt_str (e.g., a setting populated via
        # raw SQL). Return as-is.
        return value


def decrypt_json_or_legacy_plaintext(value: str) -> Any | None:
    """Decrypt a Fernet ciphertext-or-plain-JSON back to a Python object.

    Backwards-compatibility helper for the R4-PII-1 / R4-PII-2 rollout:
    rows written before encryption was wired in remain plain JSON
    strings; rows written after are Fernet ciphertexts. We try
    ciphertext first, fall back to plain JSON, return ``None`` when
    both parses fail (logged so it surfaces in observability).
    """
    if not value:
        return None
    # Try ciphertext path first.
    try:
        return json.loads(decrypt_str(value))
    except (InvalidToken, ValueError):
        pass
    # Legacy plaintext path.
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to decrypt and failed to parse plain JSON")
        return None
