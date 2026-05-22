"""Round-18 Fernet key rotation tests."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core.crypto import (
    _load_keys,
    decrypt_str,
    encrypt_str,
    get_fernet,
    rotate_ciphertext,
)


@pytest.fixture
def two_keys(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Set ENCRYPTION_KEY (new) + ENCRYPTION_KEY_OLD (old)."""
    new = Fernet.generate_key().decode()
    old = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", new)
    monkeypatch.setenv("ENCRYPTION_KEY_OLD", old)
    return new, old


@pytest.fixture
def single_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set only ENCRYPTION_KEY — no rotation."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.delenv("ENCRYPTION_KEY_OLD", raising=False)
    return key


def test_single_key_encrypts_and_decrypts(single_key: str) -> None:
    plain = "tenant-secret-value"
    cipher = encrypt_str(plain)
    assert decrypt_str(cipher) == plain


def test_two_keys_decrypt_either(two_keys: tuple[str, str]) -> None:
    """Ciphertexts produced with the old key are still readable
    while the new key is primary."""
    new, old = two_keys
    # Encrypt with the OLD key directly (simulates pre-rotation data).
    old_fernet = Fernet(old.encode())
    legacy = old_fernet.encrypt(b"legacy-imap-password").decode()

    # Now read through the rotation-aware helper — the MultiFernet
    # tries each key in order, finds the old one, decrypts.
    assert decrypt_str(legacy) == "legacy-imap-password"


def test_new_writes_use_primary_key(two_keys: tuple[str, str]) -> None:
    """New encryptions are produced with the primary key. After the
    rotation script the operator can drop the old key from the env
    and nothing breaks."""
    new, old = two_keys
    new_cipher = encrypt_str("fresh-write")

    # If we strip the old key from the rotation, decrypt still works
    # because the new write only depends on the primary.
    os.environ.pop("ENCRYPTION_KEY_OLD", None)
    assert decrypt_str(new_cipher) == "fresh-write"

    # And we can't decrypt anything that was encrypted under the old
    # key alone (sanity check).
    old_fernet = Fernet(old.encode())
    old_cipher = old_fernet.encrypt(b"old-payload").decode()
    with pytest.raises(InvalidToken):
        decrypt_str(old_cipher)


def test_rotate_ciphertext_re_encrypts_to_primary(two_keys: tuple[str, str]) -> None:
    """The rotation helper transparently re-encrypts a legacy ciphertext
    onto the primary key."""
    _, old = two_keys
    old_fernet = Fernet(old.encode())
    legacy = old_fernet.encrypt(b"smtp-secret-2025").decode()

    rotated = rotate_ciphertext(legacy)
    assert decrypt_str(rotated) == "smtp-secret-2025"

    # And the rotated form no longer decrypts under the old key alone.
    with pytest.raises(InvalidToken):
        old_fernet.decrypt(rotated.encode())


def test_load_keys_order_primary_first(two_keys: tuple[str, str]) -> None:
    new, old = two_keys
    keys = _load_keys()
    assert keys[0] == new
    assert old in keys


def test_get_fernet_returns_multifernet_when_rotation_active(
    two_keys: tuple[str, str],
) -> None:
    from cryptography.fernet import MultiFernet

    f = get_fernet()
    assert isinstance(f, MultiFernet)


def test_get_fernet_returns_single_when_only_primary(single_key: str) -> None:
    f = get_fernet()
    assert isinstance(f, Fernet)
