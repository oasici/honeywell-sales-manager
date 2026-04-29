"""Cross-tenant probe instrumentation (P3.1).

``assert_same_tenant`` raises 404 to keep the API opaque, but SOC
tooling needs to see *that* a probe happened so we can alert on
ID-enumeration patterns. The helper increments a Prometheus counter
and drops a Sentry breadcrumb on every blocked attempt; these tests
pin both signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from app.core.exceptions import NotFoundException
from app.services.tenant_context import (
    _record_cross_tenant_attempt,
    assert_same_tenant,
)


@dataclass
class _FakeRecord:
    id: int
    tenant_id: int | None


@dataclass
class _FakeUser:
    id: int
    tenant_id: int | None


def test_assert_same_tenant_emits_prometheus_counter():
    """Blocked cross-tenant access bumps the counter by 1."""
    from app.core.metrics import cross_tenant_blocked_total

    user = _FakeUser(id=42, tenant_id=1)
    record = _FakeRecord(id=99, tenant_id=2)

    before = cross_tenant_blocked_total.labels(
        user_id="42", target_tenant="2"
    )._value.get()

    with pytest.raises(NotFoundException):
        assert_same_tenant(record, user, exception_cls=NotFoundException)

    after = cross_tenant_blocked_total.labels(
        user_id="42", target_tenant="2"
    )._value.get()

    assert after == before + 1


def test_assert_same_tenant_drops_sentry_breadcrumb():
    """Every blocked attempt drops a breadcrumb so the next exception
    captured on the same thread carries the context."""
    user = _FakeUser(id=7, tenant_id=1)
    record = _FakeRecord(id=10, tenant_id=2)

    with patch("sentry_sdk.add_breadcrumb") as mock_breadcrumb:
        with pytest.raises(NotFoundException):
            assert_same_tenant(record, user, exception_cls=NotFoundException)

    mock_breadcrumb.assert_called_once()
    kwargs = mock_breadcrumb.call_args.kwargs
    assert kwargs["category"] == "security.cross_tenant"
    assert kwargs["data"]["user_id"] == 7
    assert kwargs["data"]["user_tenant"] == 1
    assert kwargs["data"]["target_tenant"] == 2


def test_same_tenant_does_not_emit_signal():
    """Legitimate same-tenant access must not pollute the counter
    or the breadcrumb stream — false positives would dwarf real
    enumeration spikes."""
    from app.core.metrics import cross_tenant_blocked_total

    user = _FakeUser(id=1, tenant_id=5)
    record = _FakeRecord(id=99, tenant_id=5)

    before = cross_tenant_blocked_total.labels(
        user_id="1", target_tenant="5"
    )._value.get()

    with patch("sentry_sdk.add_breadcrumb") as mock_breadcrumb:
        # Should not raise.
        assert_same_tenant(record, user, exception_cls=NotFoundException)

    after = cross_tenant_blocked_total.labels(
        user_id="1", target_tenant="5"
    )._value.get()
    assert after == before
    mock_breadcrumb.assert_not_called()


def test_threshold_escalation_fires_capture_message_once(monkeypatch):
    """A spike of cross-tenant blocks crosses the threshold and
    triggers a single Sentry ``capture_message`` per cooldown.
    Subsequent blocks within the cooldown stay silent."""
    from app.core.config import settings
    from app.services import tenant_context

    # Tighten the window so the test stays fast + isolated state.
    monkeypatch.setattr(settings, "CROSS_TENANT_ALERT_THRESHOLD", 3)
    monkeypatch.setattr(settings, "CROSS_TENANT_ALERT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "CROSS_TENANT_ALERT_COOLDOWN_SECONDS", 300)
    # Reset module-level state so prior tests don't poison this one.
    tenant_context._CROSS_TENANT_WINDOW.clear()
    tenant_context._CROSS_TENANT_LAST_ALERT_AT.clear()

    user = _FakeUser(id=999, tenant_id=1)
    record = _FakeRecord(id=42, tenant_id=2)

    with patch("sentry_sdk.capture_message") as mock_capture:
        # Three blocks → threshold hit → one capture.
        for _ in range(3):
            with pytest.raises(NotFoundException):
                assert_same_tenant(record, user, exception_cls=NotFoundException)

        assert mock_capture.call_count == 1
        msg = mock_capture.call_args.args[0]
        assert "user=999" in msg
        assert "3 blocks" in msg

        # More blocks within the same cooldown → still 1 capture.
        for _ in range(5):
            with pytest.raises(NotFoundException):
                assert_same_tenant(record, user, exception_cls=NotFoundException)

        assert mock_capture.call_count == 1


def test_threshold_escalation_disabled_when_zero(monkeypatch):
    """``CROSS_TENANT_ALERT_THRESHOLD=0`` turns off the escalation
    (counter + breadcrumb still fire — those are unconditional)."""
    from app.core.config import settings
    from app.services import tenant_context

    monkeypatch.setattr(settings, "CROSS_TENANT_ALERT_THRESHOLD", 0)
    tenant_context._CROSS_TENANT_WINDOW.clear()
    tenant_context._CROSS_TENANT_LAST_ALERT_AT.clear()

    user = _FakeUser(id=1001, tenant_id=1)
    record = _FakeRecord(id=42, tenant_id=2)

    with patch("sentry_sdk.capture_message") as mock_capture:
        for _ in range(20):
            with pytest.raises(NotFoundException):
                assert_same_tenant(record, user, exception_cls=NotFoundException)

        mock_capture.assert_not_called()


def test_record_helper_tolerates_missing_sdk(monkeypatch):
    """If ``sentry_sdk`` import fails (or is uninstalled in tests),
    the helper must swallow the error — observability is best-effort
    and must never break the request handler."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("no sentry in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    user = _FakeUser(id=1, tenant_id=10)
    record = _FakeRecord(id=2, tenant_id=20)
    # Must not raise — caller should still see only the
    # NotFoundException from assert_same_tenant.
    _record_cross_tenant_attempt(record, user)
