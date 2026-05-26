"""F-001 — per-tenant envelope encryption (without cloud KMS).

Today's threat model: a leaked ``ENCRYPTION_KEY`` env var
decrypts every tenant's secrets in one shot. Pre-Round-19 each
``email_credentials.password_encrypted`` row was encrypted with the
shared key, so one breach = mass breach.

Post-Round-19 model (this module):

  ┌──────────────────┐    encrypt    ┌─────────────────────┐
  │  Plaintext PW    │ ─────────────▶│ Ciphertext per-row  │
  └──────────────────┘  via DEK      └─────────────────────┘
                                             │
                                             │ DEK lives only in process
                                             │ memory (LRU cache 5 min)
                                             ▼
  ┌──────────────────┐  unwrap  ┌─────────────────────┐
  │  Wrapped DEK     │ ────────▶│ Fernet DEK (32 b)   │
  │ (per-tenant row) │  via KEK └─────────────────────┘
  └──────────────────┘
          │
          │ KEK is the app-level ``ENCRYPTION_KEY``.
          │ Future swap: an AWS KMS / Vault Transit call.
          ▼
  ┌────────────────────────┐
  │  KEK (env var today)   │
  └────────────────────────┘

Why this is a real improvement at any scale:

  * Per-tenant DEK isolation. A leaked DEK only burns one tenant.
  * KEK rotation = re-wrap N DEKs (cheap), not re-encrypt millions
    of ciphertexts (expensive).
  * KMS migration is now a one-file swap: replace ``_unwrap_dek`` /
    ``_wrap_dek`` with KMS calls. Every caller of ``encrypt_for_tenant``
    /``decrypt_for_tenant`` keeps working unchanged.

What this module does NOT do:

  * Replace the existing ``crypto.py``. The legacy API stays for
    rows already encrypted with the single key; a background
    rotation script (future Phase 5) re-encrypts those rows under
    per-tenant DEKs.
  * Persist DEKs anywhere outside the ``tenant_dek`` PG table.
    The LRU cache is in-memory only — process restart re-fetches.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from collections import OrderedDict
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_DEK_CACHE_TTL_SECONDS = 300       # 5 min
_DEK_CACHE_MAX = 1024              # fits any 20-30 user deploy comfortably
_KEK_VERSION = "env-v1"            # bumped when KEK source changes


# ── KEK provider — the swap target for KMS adoption ────────────────


def _get_kek() -> Fernet:
    """Return the active Fernet KEK.

    Today: reads the ``ENCRYPTION_KEY`` env var (same one the legacy
    ``crypto.py`` uses). Tomorrow: replace this entire function body
    with an AWS KMS / Vault Transit unwrap call. Every other function
    in this module stays untouched.
    """
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY env var missing; per-tenant DEK cannot operate"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _wrap_dek(plain_dek: bytes) -> bytes:
    """KEK-wrap a fresh DEK so it can be stored at rest."""
    return _get_kek().encrypt(plain_dek)


def _unwrap_dek(wrapped: bytes) -> bytes:
    """KEK-unwrap a stored DEK so we can use it for tenant traffic."""
    return _get_kek().decrypt(wrapped)


# ── In-process DEK cache ───────────────────────────────────────────


class _DekCache:
    """Small LRU with per-entry TTL. Thread-safe.

    Per-process. We rely on the KEK + tenant_dek table being the
    canonical source — cache eviction never causes correctness loss,
    only an extra DB round trip + KEK unwrap.
    """

    def __init__(self, max_size: int = _DEK_CACHE_MAX, ttl: int = _DEK_CACHE_TTL_SECONDS):
        self._lock = threading.Lock()
        self._data: OrderedDict[int, tuple[bytes, float]] = OrderedDict()
        self._max = max_size
        self._ttl = ttl

    def get(self, tenant_id: int) -> Optional[bytes]:
        with self._lock:
            row = self._data.get(tenant_id)
            if row is None:
                return None
            dek, deadline = row
            if time.time() > deadline:
                self._data.pop(tenant_id, None)
                return None
            self._data.move_to_end(tenant_id)
            return dek

    def put(self, tenant_id: int, dek: bytes) -> None:
        with self._lock:
            self._data[tenant_id] = (dek, time.time() + self._ttl)
            self._data.move_to_end(tenant_id)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def invalidate(self, tenant_id: int) -> None:
        with self._lock:
            self._data.pop(tenant_id, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_dek_cache = _DekCache()


# ── DEK accessors ──────────────────────────────────────────────────


async def _load_or_create_dek(db: AsyncSession, tenant_id: int) -> bytes:
    """Return the unwrapped DEK for ``tenant_id``.

    Creates a fresh DEK on first access. The create path is racy in
    theory (two concurrent requests for a new tenant), but the
    primary-key constraint on ``tenant_dek.tenant_id`` makes the
    second writer's INSERT fail, at which point we re-read.
    """
    cached = _dek_cache.get(tenant_id)
    if cached is not None:
        return cached

    row = (
        await db.execute(
            text(
                "SELECT wrapped_dek, kek_version FROM tenant_dek "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
    ).first()

    if row is not None:
        wrapped = bytes(row[0])
        try:
            dek = _unwrap_dek(wrapped)
        except InvalidToken as exc:
            raise RuntimeError(
                f"DEK for tenant {tenant_id} cannot be unwrapped — KEK "
                f"may have been rotated without re-wrapping. Run the "
                f"rotation script before any new traffic."
            ) from exc
        _dek_cache.put(tenant_id, dek)
        return dek

    # First-touch — generate a new DEK and persist its wrapped form.
    dek = Fernet.generate_key()
    wrapped = _wrap_dek(dek)
    try:
        await db.execute(
            text(
                """
                INSERT INTO tenant_dek (tenant_id, wrapped_dek, kek_version)
                VALUES (:tid, :wrapped, :ver)
                """
            ),
            {"tid": tenant_id, "wrapped": wrapped, "ver": _KEK_VERSION},
        )
        await db.flush()
    except Exception:
        # Concurrent creator won. Re-read.
        await db.rollback()
        row = (
            await db.execute(
                text(
                    "SELECT wrapped_dek FROM tenant_dek "
                    "WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            )
        ).first()
        if row is None:
            raise
        dek = _unwrap_dek(bytes(row[0]))
    _dek_cache.put(tenant_id, dek)
    return dek


async def encrypt_for_tenant(
    db: AsyncSession, tenant_id: int, plaintext: bytes | str
) -> bytes:
    """Encrypt ``plaintext`` under the tenant's DEK.

    Returns Fernet ciphertext (begins with ``gAAAAA``). Idempotent
    in the sense that two calls with the same plaintext produce
    different ciphertexts (Fernet nonces) — that's correct and
    matches the legacy ``crypto.encrypt_password`` contract.
    """
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    dek = await _load_or_create_dek(db, tenant_id)
    return Fernet(dek).encrypt(plaintext)


async def decrypt_for_tenant(
    db: AsyncSession, tenant_id: int, ciphertext: bytes
) -> bytes:
    """Inverse of :func:`encrypt_for_tenant`."""
    dek = await _load_or_create_dek(db, tenant_id)
    return Fernet(dek).decrypt(ciphertext)


async def rotate_tenant_dek(
    db: AsyncSession, tenant_id: int
) -> None:
    """Generate a new DEK for ``tenant_id`` and re-wrap.

    Caller is responsible for re-encrypting any persisted ciphertext
    rows owned by this tenant — this function only rotates the key,
    not the data. Use the future ``scripts/rotate_tenant_dek.py``
    helper to do the full re-encrypt sweep transactionally.
    """
    new_dek = Fernet.generate_key()
    wrapped = _wrap_dek(new_dek)
    await db.execute(
        text(
            """
            UPDATE tenant_dek
               SET wrapped_dek = :wrapped,
                   kek_version = :ver,
                   rotated_at  = now()
             WHERE tenant_id   = :tid
            """
        ),
        {"wrapped": wrapped, "ver": _KEK_VERSION, "tid": tenant_id},
    )
    await db.flush()
    _dek_cache.invalidate(tenant_id)
