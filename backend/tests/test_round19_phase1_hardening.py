"""Round-19 Phase 1 hardening tests.

Covers F-002, F-003, F-004, F-008, F-016, F-019, F-020.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.csv_sanitizer import sanitize_csv_cell, sanitize_csv_row
from app.services.email_rfq_aggregator import (
    _sender_email_normalised,
    _time_bucket,
    compute_rfq_thread_key,
)


# ────────────────────────────────────────────────────────────────────
# F-008 — CSV/Excel injection sanitiser
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("=cmd|'/c calc.exe'!A1", "'=cmd|'/c calc.exe'!A1"),
        ("+1+1", "'+1+1"),
        ("-2*A1", "'-2*A1"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\t=evil", "'\t=evil"),
        ("\r=evil", "'\r=evil"),
        ("   =leading space", "'   =leading space"),  # leading whitespace then trigger
        # Safe cases:
        ("Acme Inc", "Acme Inc"),
        ("foo=bar", "foo=bar"),  # = not in leading position
        ("100", "100"),
        ("", ""),
    ],
)
def test_csv_sanitiser_prefixes_formula_triggers(raw: str, expected: str) -> None:
    assert sanitize_csv_cell(raw) == expected


def test_csv_sanitiser_handles_non_string_scalars() -> None:
    assert sanitize_csv_cell(None) == ""
    assert sanitize_csv_cell(42) == "42"
    assert sanitize_csv_cell(3.14) == "3.14"
    assert sanitize_csv_cell(True) == "True"


def test_csv_sanitiser_is_idempotent() -> None:
    once = sanitize_csv_cell("=cmd")
    twice = sanitize_csv_cell(once)
    # Already prefixed values do not gain a second apostrophe because
    # the leading char becomes ``'`` which is not a trigger.
    assert twice == once


def test_sanitize_csv_row_returns_strings_only() -> None:
    out = sanitize_csv_row(["=evil", 42, None, "ok"])
    assert out == ["'=evil", "42", "", "ok"]
    assert all(isinstance(x, str) for x in out)


# ────────────────────────────────────────────────────────────────────
# F-016 — RFQ aggregation: sender_email + 14-day bucket
# ────────────────────────────────────────────────────────────────────


class _StubEmail:
    """Lightweight stand-in for ``EmailRequest`` in unit tests."""

    def __init__(
        self,
        tenant_id: int = 1,
        thread_id: str | None = None,
        from_address: str = "buyer@acme.com",
        subject: str | None = "Acil parça istegi",
        received_at: datetime | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.thread_id = thread_id
        self.from_address = from_address
        self.subject = subject
        self.received_at = received_at or datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_sender_email_normalised_strips_and_lowercases() -> None:
    assert _sender_email_normalised("  Ahmet@Acme.COM  ") == "ahmet@acme.com"
    assert _sender_email_normalised(None) == ""
    assert _sender_email_normalised("") == ""


def test_rfq_key_same_thread_id_groups() -> None:
    e1 = _StubEmail(thread_id="t-123")
    e2 = _StubEmail(thread_id="t-123", received_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert compute_rfq_thread_key(e1) == compute_rfq_thread_key(e2)


def test_rfq_key_fallback_separates_different_senders_same_subject() -> None:
    e1 = _StubEmail(from_address="ahmet@acme.com")
    e2 = _StubEmail(from_address="mehmet@acme.com")
    # Same domain but different addresses → different threads.
    assert compute_rfq_thread_key(e1) != compute_rfq_thread_key(e2)


def test_rfq_key_is_time_independent() -> None:
    """The hash itself no longer carries time — the 14-day window is
    enforced at query time (``list_emails_in_rfq``) so a subject
    reused 6 months later gets the same key but is filtered out by
    the cutoff. This avoids the boundary-straddle bug where two
    emails 9 days apart got *different* keys because they fell on
    opposite sides of a fixed 14-day boundary.
    """
    e_may = _StubEmail(received_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
    e_nov = _StubEmail(received_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert compute_rfq_thread_key(e_may) == compute_rfq_thread_key(e_nov)


def test_rfq_key_respects_tenant_isolation() -> None:
    e1 = _StubEmail(tenant_id=1)
    e2 = _StubEmail(tenant_id=2)
    assert compute_rfq_thread_key(e1) != compute_rfq_thread_key(e2)


# ────────────────────────────────────────────────────────────────────
# F-002 / F-003 / F-004 — auto-quote eligibility gate
# ────────────────────────────────────────────────────────────────────


from app.services.email_processing_service import _auto_quote_eligible


class _GateStub:
    """Stand-in for ``EmailRequest`` for gate unit tests."""

    def __init__(
        self,
        sender_auth_status: str = "pass",
        attachment_pages_truncated: bool = False,
        first_time_sender: bool = False,
    ) -> None:
        self.sender_auth_status = sender_auth_status
        self.attachment_pages_truncated = attachment_pages_truncated
        self.first_time_sender = first_time_sender


def _parts_all_exact(n: int = 2) -> dict:
    return {
        "parts": [
            {"part_code": f"C7061A101{i}", "catalog_status": "exact"} for i in range(n)
        ]
    }


def test_gate_passes_clean_email() -> None:
    eligible, reason = _auto_quote_eligible(_GateStub(), _parts_all_exact())
    assert eligible is True
    assert reason is None


def test_gate_blocks_auth_not_pass() -> None:
    eligible, reason = _auto_quote_eligible(
        _GateStub(sender_auth_status="fail"), _parts_all_exact()
    )
    assert eligible is False
    assert reason == "auth_not_pass"


def test_gate_blocks_ocr_truncated() -> None:
    eligible, reason = _auto_quote_eligible(
        _GateStub(attachment_pages_truncated=True), _parts_all_exact()
    )
    assert eligible is False
    assert reason == "ocr_truncated"


def test_gate_blocks_first_time_sender() -> None:
    eligible, reason = _auto_quote_eligible(
        _GateStub(first_time_sender=True), _parts_all_exact()
    )
    assert eligible is False
    assert reason == "first_time_sender"


def test_gate_blocks_fuzzy_part() -> None:
    parsed = {
        "parts": [
            {"part_code": "C7061A1012", "catalog_status": "exact"},
            {"part_code": "RM7895A1014", "catalog_status": "fuzzy"},
        ]
    }
    eligible, reason = _auto_quote_eligible(_GateStub(), parsed)
    assert eligible is False
    assert reason == "fuzzy_or_unknown"


def test_gate_blocks_unknown_part() -> None:
    parsed = {"parts": [{"part_code": "XYZ", "catalog_status": "unknown"}]}
    eligible, reason = _auto_quote_eligible(_GateStub(), parsed)
    assert eligible is False
    assert reason == "fuzzy_or_unknown"


def test_gate_priority_auth_beats_ocr() -> None:
    """auth_not_pass should be reported even when OCR is also truncated."""
    eligible, reason = _auto_quote_eligible(
        _GateStub(sender_auth_status="fail", attachment_pages_truncated=True),
        _parts_all_exact(),
    )
    assert eligible is False
    assert reason == "auth_not_pass"
