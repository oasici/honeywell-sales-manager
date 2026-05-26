"""Round-19 Phase 8 — roadmap execution tests.

Covers:
  D-006  Persistent login rate limiter
  D-008  Per-tenant at_risk_threshold setting
  D-010  Cross-tenant probe audit log
  D-014  Sign-OTP wired to real SMTP (smoke)
  D-016  KVKK export worker (smoke)
  D-019  DLQ writer + admin endpoints (smoke)
  D-024  Sequence unsubscribe placement validator
  D-029  Approval delegation expiry cron
  D-033  Customer Health zero-data bias correction
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ────────────────────────────────────────────────────────────────────
# D-006 — Login rate limiter (pure logic via in-memory state)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_rate_limiter_records_and_locks(db) -> None:
    from app.services.login_rate_limiter import (
        MAX_ATTEMPTS,
        is_locked,
        record_failure,
        record_success,
        _reset_for_tests,
    )

    _reset_for_tests()
    email = "attacker@example.com"
    assert await is_locked(db, email) is False

    # Four failures — still not locked.
    for _ in range(MAX_ATTEMPTS - 1):
        locked = await record_failure(db, email)
        assert locked is False
    assert await is_locked(db, email) is False

    # Fifth failure → locked.
    locked = await record_failure(db, email)
    assert locked is True
    assert await is_locked(db, email) is True

    # record_success clears both layers.
    await record_success(db, email)
    assert await is_locked(db, email) is False


@pytest.mark.asyncio
async def test_login_rate_limiter_survives_memory_reset(db) -> None:
    """The PG layer carries the lockout across process restart."""
    from app.services.login_rate_limiter import (
        MAX_ATTEMPTS,
        is_locked,
        record_failure,
        _reset_for_tests,
    )

    _reset_for_tests()
    email = "persistent@example.com"
    for _ in range(MAX_ATTEMPTS):
        await record_failure(db, email)
    assert await is_locked(db, email) is True

    # Simulate process restart by wiping in-memory state.
    _reset_for_tests()
    # PG row remains; the next is_locked() call re-hydrates it.
    assert await is_locked(db, email) is True


# ────────────────────────────────────────────────────────────────────
# D-008 — at_risk_threshold setting
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_settings_has_at_risk_threshold_default(db) -> None:
    from app.services.tenant_settings_service import get_tenant_settings

    cfg = await get_tenant_settings(db, tenant_id=1)
    # Default for a tenant with no row.
    assert cfg.at_risk_threshold == 40


# ────────────────────────────────────────────────────────────────────
# D-024 — Sequence body validator placement check
# ────────────────────────────────────────────────────────────────────


def test_sequence_unsubscribe_in_html_comment_rejected() -> None:
    from app.services.sequence_unsubscribe import (
        SequenceValidationError,
        validate_sequence_body,
    )

    body = (
        "Merhaba,\n"
        "Fiyat listemiz ektedir.\n"
        "<!-- gizli unsubscribe: {{unsubscribe_link}} -->\n"
    )
    with pytest.raises(SequenceValidationError, match="in_comment"):
        validate_sequence_body(body)


def test_sequence_unsubscribe_visible_token_accepted() -> None:
    from app.services.sequence_unsubscribe import validate_sequence_body

    body = "Merhaba,\n...\nÇıkmak için: {{unsubscribe_link}}\n"
    validate_sequence_body(body)


# ────────────────────────────────────────────────────────────────────
# D-033 — Customer health zero-data bias correction (pure)
# ────────────────────────────────────────────────────────────────────


from app.services.health_bias_correction import (
    correct_for_data_sparsity,
    is_displayable_in_at_risk,
)


def test_no_data_customer_returns_neutral_50() -> None:
    score = correct_for_data_sparsity(raw_score=0, signal_count=0)
    assert score.value == 50
    assert score.confidence == 0.0


def test_sparse_data_returns_neutral() -> None:
    """signal_count=1/6 = 0.17 < 0.3 → still neutral."""
    score = correct_for_data_sparsity(raw_score=15, signal_count=1)
    assert score.value == 50
    assert pytest.approx(score.confidence, 0.01) == 1 / 6


def test_full_data_passes_through() -> None:
    score = correct_for_data_sparsity(raw_score=42, signal_count=6)
    assert score.value == 42
    assert score.confidence == 1.0


def test_at_risk_filter_hides_low_confidence() -> None:
    no_data = correct_for_data_sparsity(raw_score=10, signal_count=0)
    # Even though raw < threshold, confidence too low to display
    assert is_displayable_in_at_risk(no_data, threshold=40) is False

    real_at_risk = correct_for_data_sparsity(raw_score=20, signal_count=6)
    assert is_displayable_in_at_risk(real_at_risk, threshold=40) is True

    healthy = correct_for_data_sparsity(raw_score=80, signal_count=6)
    assert is_displayable_in_at_risk(healthy, threshold=40) is False


# ────────────────────────────────────────────────────────────────────
# D-010 — Cross-tenant probe audit
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_recorder_silent_on_truly_missing(db, admin_user) -> None:
    from app.services.cross_tenant_audit import (
        count_recent_probes,
        maybe_record_probe,
    )

    before = await count_recent_probes(db, user_id=admin_user.id)
    await maybe_record_probe(
        db,
        user_id=admin_user.id,
        user_tenant=admin_user.tenant_id,
        entity="customer",
        entity_id=999999999,   # truly missing
    )
    after = await count_recent_probes(db, user_id=admin_user.id)
    assert after == before        # no record for genuine misses


# ────────────────────────────────────────────────────────────────────
# D-019 — DLQ writer
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dlq_write_and_list(db, admin_user) -> None:
    from app.services.dlq_service import (
        count_unresolved,
        list_unresolved,
        mark_resolved,
        write_to_dlq,
    )

    before = await count_unresolved(db)
    new_id = await write_to_dlq(
        db,
        job_name="test_job",
        error="simulated failure",
        payload={"step": 1},
    )
    await db.commit()
    after = await count_unresolved(db)
    assert after == before + 1

    entries = await list_unresolved(db)
    assert any(e.id == new_id for e in entries)

    await mark_resolved(db, dlq_id=new_id, user_id=admin_user.id, note="handled")
    await db.commit()
    later = await count_unresolved(db)
    assert later == after - 1


# ────────────────────────────────────────────────────────────────────
# D-029 — Delegation expiry cron (logic check, not full schedule)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delegation_expiry_cron_clears_past_due(db, admin_user) -> None:
    from sqlalchemy import text

    # Insert a stub approval_rule with expired delegation. Use the
    # admin_user as the delegate target so the FK is satisfied.
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.execute(text(
        "INSERT INTO approval_rules "
        "  (name, entity_type, condition_type, threshold_value, threshold_operator, "
        "   chain_mode, priority, is_active, delegate_to, delegate_until, created_at) "
        "VALUES "
        "  ('Expired', 'quote', 'discount_pct', 30, 'gt', "
        "   'sequential', 0, true, :uid, :past, now()),"
        "  ('Future', 'quote', 'discount_pct', 30, 'gt', "
        "   'sequential', 0, true, :uid, :future, now())"
    ), {"past": past, "future": future, "uid": admin_user.id})
    await db.commit()

    from app.tasks.scheduler import r19_delegation_expiry_task

    await r19_delegation_expiry_task()

    # The past-due row should be cleared.
    rows = (await db.execute(text(
        "SELECT name, delegate_until FROM approval_rules "
        "WHERE name IN ('Expired', 'Future')"
    ))).all()
    by_name = {r[0]: r[1] for r in rows}
    assert by_name["Expired"] is None
    assert by_name["Future"] is not None


# ────────────────────────────────────────────────────────────────────
# D-014, D-016 — Smoke / surface checks
# ────────────────────────────────────────────────────────────────────


def test_smtp_service_module_surface() -> None:
    from app.services import smtp_service
    assert callable(smtp_service.send_email)
    assert callable(smtp_service.send_email_sync)


def test_kvkk_export_worker_module_surface() -> None:
    from app.services import kvkk_export_worker
    assert callable(kvkk_export_worker.run_export)


def test_sign_otp_uses_real_smtp_wired() -> None:
    """The Phase 5 stub was DEBUG-log; D-014 swapped for send_email_sync."""
    import inspect
    from app.api.v1 import sign_otp

    src = inspect.getsource(sign_otp._send_otp_email)
    assert "send_email_sync" in src
    assert "logger.debug" not in src or "SMTP send failed" in src
