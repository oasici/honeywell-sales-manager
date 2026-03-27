"""TDD tests for core security module."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from app.core.security import (
    _revoked_jti,
    create_access_token,
    decode_token,
    hash_password,
    is_safe_path,
    revoke_token,
    sanitize_filename,
    validate_password_strength,
    verify_password,
)


# ── Fixtures ──

TEST_JWT_SECRET = "test-secret-key-for-unit-tests-only"
TEST_JWT_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def _patch_settings():
    """Patch JWT settings for all tests in this module."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.JWT_SECRET_KEY = TEST_JWT_SECRET
        mock_settings.JWT_ALGORITHM = TEST_JWT_ALGORITHM
        mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7
        yield mock_settings


@pytest.fixture(autouse=True)
def _clear_revoked_tokens():
    """Ensure revoked token set is clean for each test."""
    _revoked_jti.clear()
    yield
    _revoked_jti.clear()


# ── Password Hashing ──

class TestPasswordHashing:
    """Test cycles 1 and 2: hash and verify passwords."""

    def test_should_hash_and_verify_password(self):
        password = "SecurePass123"
        hashed = hash_password(password)

        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_should_reject_wrong_password(self):
        hashed = hash_password("CorrectPassword1")

        assert verify_password("WrongPassword1", hashed) is False

    def test_should_produce_different_hashes_for_same_password(self):
        password = "SamePassword1"
        hash_1 = hash_password(password)
        hash_2 = hash_password(password)

        assert hash_1 != hash_2
        assert verify_password(password, hash_1) is True
        assert verify_password(password, hash_2) is True


# ── Password Strength Validation ──

class TestPasswordStrength:
    """Test cycles 3, 4, 5, 6: password strength validation."""

    def test_should_validate_password_strength_min_length(self):
        result = validate_password_strength("Ab1")

        assert result is not None
        assert "8" in result

    def test_should_validate_password_requires_uppercase(self):
        result = validate_password_strength("lowercase1only")

        assert result is not None

    def test_should_validate_password_requires_digit(self):
        result = validate_password_strength("NoDigitsHere")

        assert result is not None

    def test_should_accept_strong_password(self):
        result = validate_password_strength("StrongPass1")

        assert result is None

    def test_should_reject_password_without_lowercase(self):
        result = validate_password_strength("ALLUPPERCASE1")

        assert result is not None


# ── JWT Tokens ──

class TestJwtTokens:
    """Test cycles 7, 8, 9: create, decode, expire, revoke tokens."""

    def test_should_create_and_decode_access_token(self):
        data = {"sub": "user@example.com", "user_id": 42}
        token = create_access_token(data)

        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == "user@example.com"
        assert payload["user_id"] == 42
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_should_reject_expired_token(self):
        data = {"sub": "user@example.com"}
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))

        payload = decode_token(token)

        assert payload is None

    def test_should_revoke_token(self):
        data = {"sub": "user@example.com"}
        token = create_access_token(data)

        payload_before = decode_token(token)
        assert payload_before is not None

        revoke_token(token)

        payload_after = decode_token(token)
        assert payload_after is None

    def test_should_decode_different_tokens_independently(self):
        token_1 = create_access_token({"sub": "user1@example.com"})
        token_2 = create_access_token({"sub": "user2@example.com"})

        revoke_token(token_1)

        assert decode_token(token_1) is None
        assert decode_token(token_2) is not None

    def test_should_return_none_for_invalid_token(self):
        assert decode_token("not-a-valid-token") is None


# ── Filename Sanitization ──

class TestSanitizeFilename:
    """Test cycle 10: sanitize filenames."""

    def test_should_sanitize_filename_removing_path_traversal(self):
        result = sanitize_filename("../../../etc/passwd")

        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result

    def test_should_remove_null_bytes(self):
        result = sanitize_filename("file\x00name.txt")

        assert "\x00" not in result

    def test_should_return_default_for_empty_result(self):
        result = sanitize_filename("...")

        assert result == "uploaded_file"

    def test_should_keep_normal_filenames(self):
        result = sanitize_filename("report.pdf")

        assert result == "report.pdf"


# ── Safe Path Check ──

class TestIsSafePath:
    """Test cycle 11: is_safe_path rejects traversal."""

    def test_should_detect_unsafe_path(self):
        base = "/var/app/uploads"
        target = "/var/app/uploads/../../etc/passwd"

        assert is_safe_path(base, target) is False

    def test_should_accept_safe_path(self):
        base = "/var/app/uploads"
        target = "/var/app/uploads/user_files/report.pdf"

        assert is_safe_path(base, target) is True

    def test_should_accept_base_dir_itself(self):
        base = "/var/app/uploads"

        assert is_safe_path(base, base) is True
