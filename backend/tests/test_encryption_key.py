"""P0-2: ENCRYPTION_KEY production guard tests."""

import os
import pytest


def test_encryption_key_required_in_production(monkeypatch):
    """In production, missing ENCRYPTION_KEY must raise RuntimeError."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    # Patch settings to production mode
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENV", "production")

    from app.api.v1.settings import _get_fernet
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY must be set in production"):
        _get_fernet()


def test_encryption_key_auto_generated_in_development(monkeypatch):
    """In development, ENCRYPTION_KEY is auto-generated if missing."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    from app.core.config import settings
    monkeypatch.setattr(settings, "ENV", "development")

    from app.api.v1.settings import _get_fernet
    fernet = _get_fernet()
    assert fernet is not None
    # Key should now be set in env
    assert os.environ.get("ENCRYPTION_KEY")


def test_encrypt_decrypt_roundtrip(monkeypatch):
    """Encrypt then decrypt should return the original value."""
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", test_key)

    from app.api.v1.settings import _encrypt_password, _decrypt_password
    original = "my-secret-password"
    encrypted = _encrypt_password(original)
    decrypted = _decrypt_password(encrypted)
    assert decrypted == original
    assert encrypted != original
