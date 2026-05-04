"""Symmetric encryption helpers (Fernet) for at-rest secrets.

Round-4 R4-PII-1 / R4-PII-2 lifted these helpers out of
``app/api/v1/settings.py`` so multiple services can share them without
circular imports — the calendar OAuth token store and the e-sign
provider config writer both need ``encrypt_str`` / ``decrypt_str``.

Key resolution mirrors the legacy site:

- ``ENCRYPTION_KEY`` env var wins (production).
- In dev/test, persist a generated key to ``data/.encryption_key`` so
  multiple workers + restarts share the same key. This is the
  R4-PII-3 fix — previously the key was only set in ``os.environ``,
  which evaporated on restart and rendered all encrypted SMTP
  passwords undecryptable.

The legacy ``_encrypt_password`` / ``_decrypt_password`` in
``settings.py`` continue to work via re-export.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEY_FILE = os.path.join("data", ".encryption_key")


def get_fernet() -> Fernet:
    """Return a Fernet instance keyed by ``ENCRYPTION_KEY``.

    Raises in production when the key is unset; in dev/test, generates
    and persists one so subsequent restarts can decrypt prior writes.
    """
    from app.core.config import settings as cfg

    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        if cfg.is_production:
            raise RuntimeError(
                "ENCRYPTION_KEY must be set in production. "
                "Generate one with: python -c \"from cryptography.fernet "
                "import Fernet; print(Fernet.generate_key().decode())\""
            )
        # Dev/test: persist key to disk so workers + restarts share it.
        if os.path.exists(_KEY_FILE):
            with open(_KEY_FILE) as fh:
                key = fh.read().strip()
        if not key:
            key = Fernet.generate_key().decode()
            os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
            with open(_KEY_FILE, "w") as fh:
                fh.write(key)
        os.environ["ENCRYPTION_KEY"] = key
    return Fernet(key.encode() if isinstance(key, str) else key)


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
