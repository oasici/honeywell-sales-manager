"""Round-19 Phase 4 hardening tests.

Covers F-001, F-005, F-006, F-007, F-011, F-023, F-024.

These tests are deliberately split into pure-Python (no-DB) and
async-PG sections. The pure tests exercise the policy / state-machine
logic; the async ones touch the new tables to verify the DDL is
sane + the integrity constraints fire correctly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest


# ────────────────────────────────────────────────────────────────────
# F-007 — Soft delete (pure)
# ────────────────────────────────────────────────────────────────────


from app.services.soft_delete import (
    SoftDeleteRefused,
    anonymise_user_pii,
    is_deleted,
    mark_deleted,
    refuse_if_has_active,
    restore,
)


@dataclass
class _Tombstone:
    deleted_at: datetime | None = None
    deleted_by: int | None = None
    delete_reason: str | None = None


def test_mark_deleted_writes_tombstone() -> None:
    row = _Tombstone()
    mark_deleted(row, actor_id=42, reason="Inactive customer")
    assert is_deleted(row) is True
    assert row.deleted_by == 42
    assert row.delete_reason == "Inactive customer"


def test_mark_deleted_is_idempotent() -> None:
    row = _Tombstone()
    mark_deleted(row, actor_id=1, reason="first")
    first_at = row.deleted_at
    # Second delete after a short while — original timestamp preserved.
    mark_deleted(row, actor_id=99, reason="second")
    assert row.deleted_at == first_at
    assert row.deleted_by == 1                  # original actor preserved
    assert row.delete_reason == "first"


def test_restore_clears_tombstone() -> None:
    row = _Tombstone()
    mark_deleted(row, actor_id=1)
    restore(row)
    assert is_deleted(row) is False
    assert row.deleted_by is None
    assert row.delete_reason is None


def test_refuse_if_has_active_blocks_with_dependents() -> None:
    with pytest.raises(SoftDeleteRefused) as exc_info:
        refuse_if_has_active(
            entity="Customer",
            id_=1,
            dependent_counts={"opportunities": 3, "quotes": 0, "invoices": 1},
        )
    err = exc_info.value
    assert err.dependents == {"opportunities": 3, "invoices": 1}


def test_refuse_if_has_active_passes_with_no_dependents() -> None:
    refuse_if_has_active(
        entity="Customer", id_=1, dependent_counts={"opps": 0, "quotes": 0}
    )


def test_refuse_if_has_active_force_bypass() -> None:
    refuse_if_has_active(
        entity="Customer",
        id_=1,
        dependent_counts={"opportunities": 99},
        allow_force=True,
    )


def test_anonymise_user_pii() -> None:
    @dataclass
    class _User:
        id: int = 42
        email: str = "user@example.com"
        full_name: str = "Real Name"
        phone: str = "+90 555 1111111"
        password_hash: str = "$2b$12$realhash"
        is_active: bool = True

    u = _User()
    anonymise_user_pii(u)
    assert u.email == "deleted-42@anonymised.local"
    assert u.full_name == "deleted-user-42"
    assert u.phone is None
    assert u.password_hash.startswith("!disabled:")
    assert u.is_active is False


# ────────────────────────────────────────────────────────────────────
# F-011 — Role split (pure parts)
# ────────────────────────────────────────────────────────────────────


from app.services.role_split import (
    LEGACY_OPS_SUBROLES,
    ROLE_OPS_AUDIT,
    ROLE_OPS_BILLING,
    ROLE_OPS_DATA,
    ROLE_OPS_USERS,
    SodViolation,
    find_sod_violations,
)


def test_sod_audit_plus_users_is_a_violation() -> None:
    violations = find_sod_violations({ROLE_OPS_AUDIT, ROLE_OPS_USERS})
    assert len(violations) == 1
    assert violations[0].role_a == ROLE_OPS_AUDIT


def test_sod_safe_combination_returns_empty() -> None:
    assert find_sod_violations({ROLE_OPS_USERS, ROLE_OPS_DATA}) == []


def test_sod_multiple_conflicts_all_surfaced() -> None:
    violations = find_sod_violations({ROLE_OPS_AUDIT, ROLE_OPS_USERS, ROLE_OPS_BILLING, ROLE_OPS_DATA})
    assert len(violations) == 3


def test_legacy_subrole_set_unchanged() -> None:
    """Migration relies on this exact set. Lock it down."""
    assert LEGACY_OPS_SUBROLES == frozenset({"ops_users", "ops_data", "ops_billing"})


# ────────────────────────────────────────────────────────────────────
# F-024 — Sequence unsubscribe validation (pure)
# ────────────────────────────────────────────────────────────────────


from app.services.sequence_unsubscribe import (
    SequenceValidationError,
    issue_unsubscribe_token,
    render_unsubscribe_link,
    validate_sequence_body,
)


def test_sequence_body_missing_token_rejected() -> None:
    with pytest.raises(SequenceValidationError, match="unsubscribe"):
        validate_sequence_body(
            "Merhaba {{first_name}},\nFiyat listemiz ektedir.\n"
        )


def test_sequence_body_with_token_accepted() -> None:
    validate_sequence_body(
        "Merhaba,\n...\n\nÇıkmak için: {{unsubscribe_link}}"
    )


def test_sequence_body_empty_rejected() -> None:
    with pytest.raises(SequenceValidationError, match="empty"):
        validate_sequence_body("")
    with pytest.raises(SequenceValidationError, match="empty"):
        validate_sequence_body("   \n")


def test_sequence_body_token_matches_case_insensitive_and_whitespace() -> None:
    validate_sequence_body("... {{ UNSUBSCRIBE_LINK }} ...")
    validate_sequence_body("... {{unsubscribe_link}} ...")


def test_unsubscribe_token_is_url_safe_and_unique() -> None:
    t1 = issue_unsubscribe_token()
    t2 = issue_unsubscribe_token()
    assert t1.plaintext != t2.plaintext
    # url-safe base64: only [A-Za-z0-9_-].
    import re
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", t1.plaintext)


def test_render_unsubscribe_link_uses_base_url() -> None:
    url = render_unsubscribe_link(base_url="https://example.com/", token="abc")
    assert url == "https://example.com/unsubscribe/abc"


# ────────────────────────────────────────────────────────────────────
# F-006 — Sign OTP (pure parts)
# ────────────────────────────────────────────────────────────────────


from app.services.sign_otp import (
    MAX_OTP_ATTEMPTS,
    MAX_OTP_SENDS_PER_TOKEN,
    OTP_VALID_MINUTES,
    TOKEN_TTL_DAYS,
    SignTokenError,
    _mask_email,
    _gen_otp,
)


def test_mask_email_preserves_domain() -> None:
    assert _mask_email("ahmet@acme.com") == "a***@acme.com"
    assert _mask_email("a@x.com") == "***@x.com"


def test_otp_is_six_digit_zero_padded() -> None:
    otp = _gen_otp()
    assert len(otp) == 6
    assert otp.isdigit()
    # Statistical: across many samples we should hit some starting with 0
    samples = [_gen_otp() for _ in range(2000)]
    assert any(s.startswith("0") for s in samples)


def test_sign_token_error_carries_reason() -> None:
    exc = SignTokenError("otp_locked", detail="Too many wrong attempts")
    assert exc.reason == "otp_locked"
    assert "wrong" in str(exc)


def test_otp_constants_are_security_sane() -> None:
    """Lock the security envelope. Changing these requires a thread."""
    assert TOKEN_TTL_DAYS <= 14, "Token TTL too long; weakens binding"
    assert MAX_OTP_SENDS_PER_TOKEN <= 5, "Too many OTP sends invites abuse"
    assert MAX_OTP_ATTEMPTS <= 5, "Too many wrong-OTP tries weakens brute-force margin"
    assert OTP_VALID_MINUTES <= 15, "OTP validity window too long"


# ────────────────────────────────────────────────────────────────────
# F-023 — KVKK two-person (pure parts)
# ────────────────────────────────────────────────────────────────────


from app.services.kvkk_two_person import StateError, SUBJECT_KINDS


def test_kvkk_subject_kinds_are_expected_set() -> None:
    assert set(SUBJECT_KINDS) == {"email", "vergi_no", "phone"}


def test_kvkk_state_error_is_truthy_exception() -> None:
    assert issubclass(StateError, Exception)


# ────────────────────────────────────────────────────────────────────
# F-001 — Per-tenant DEK (pure parts of the surface)
# ────────────────────────────────────────────────────────────────────


def test_crypto_v2_module_surface_intact() -> None:
    from app.core import crypto_v2

    assert callable(crypto_v2.encrypt_for_tenant)
    assert callable(crypto_v2.decrypt_for_tenant)
    assert callable(crypto_v2.rotate_tenant_dek)


def test_dek_cache_evicts_after_ttl(monkeypatch) -> None:
    """Local cache should drop entries past their TTL."""
    from app.core.crypto_v2 import _DekCache
    cache = _DekCache(max_size=10, ttl=1)
    cache.put(tenant_id=1, dek=b"k1")
    assert cache.get(1) == b"k1"
    import time as _time
    _time.sleep(1.05)
    assert cache.get(1) is None


def test_dek_cache_lru_eviction() -> None:
    from app.core.crypto_v2 import _DekCache
    cache = _DekCache(max_size=2, ttl=60)
    cache.put(1, b"a")
    cache.put(2, b"b")
    cache.put(3, b"c")   # should evict 1
    assert cache.get(1) is None
    assert cache.get(2) == b"b"
    assert cache.get(3) == b"c"


# ────────────────────────────────────────────────────────────────────
# F-005 — Admin nonce (pure parts)
# ────────────────────────────────────────────────────────────────────


def test_admin_nonce_module_surface() -> None:
    from app.services import admin_nonce

    assert callable(admin_nonce.issue_nonce)
    assert callable(admin_nonce.consume_nonce)
    assert callable(admin_nonce.cleanup_expired_nonces)
    assert admin_nonce.NONCE_TTL_MINUTES <= 15  # short TTL is the point
