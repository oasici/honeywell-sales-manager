"""Shared Fernet encryption for sensitive values (ERP credentials, passwords, tokens).

Single source of truth so the same ENCRYPTION_KEY is used across modules
(settings email passwords, ERP credentials, API tokens).

Key resolution order:
    1. `ENCRYPTION_KEY` environment variable.
    2. Development fallback: persisted key at `data/.encryption_key`
       (never enabled in production — raises RuntimeError instead).

Rotation: generate a new key with
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
and set `ENCRYPTION_KEY_PREVIOUS` to decrypt legacy records during migration.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEV_KEY_FILE = os.path.join("data", ".encryption_key")


def _load_dev_key() -> str:
    """Load or generate the development-only key file."""
    if os.path.exists(_DEV_KEY_FILE):
        with open(_DEV_KEY_FILE, encoding="utf-8") as fh:
            key = fh.read().strip()
            if key:
                return key
    key = Fernet.generate_key().decode()
    os.makedirs(os.path.dirname(_DEV_KEY_FILE), exist_ok=True)
    with open(_DEV_KEY_FILE, "w", encoding="utf-8") as fh:
        fh.write(key)
    return key


@lru_cache(maxsize=1)
def get_fernet() -> MultiFernet:
    """Return a MultiFernet that can decrypt legacy records during rotation."""
    primary = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not primary:
        if settings.is_production:
            raise RuntimeError(
                "ENCRYPTION_KEY must be set in production. Generate one with "
                "`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`"
            )
        primary = _load_dev_key()
        os.environ["ENCRYPTION_KEY"] = primary

    keys: list[Fernet] = [Fernet(primary.encode())]
    previous = os.environ.get("ENCRYPTION_KEY_PREVIOUS", "").strip()
    if previous:
        keys.append(Fernet(previous.encode()))
    return MultiFernet(keys)


def encrypt_str(plain: str) -> str:
    """Encrypt a UTF-8 string; returns the base64 token."""
    return get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_str(token: str) -> str:
    """Decrypt a token produced by ``encrypt_str``."""
    try:
        return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encryption token or rotated key") from exc


def encrypt_json(payload: dict) -> str:
    """Serialize dict to JSON then encrypt."""
    return encrypt_str(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def decrypt_json(token: str) -> dict:
    """Decrypt an encrypted JSON blob back into a dict."""
    return json.loads(decrypt_str(token))
