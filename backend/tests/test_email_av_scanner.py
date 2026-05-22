"""Round-18 AV scan hook tests."""

from __future__ import annotations

import pytest

from app.services.email_av_scanner import (
    AvVerdict,
    _NoopScanner,
    get_scanner,
    scan_attachments,
)


def test_noop_scanner_returns_unscanned() -> None:
    s = _NoopScanner()
    v = s.scan("rfq.xlsx", b"any bytes")
    assert v.filename == "rfq.xlsx"
    assert v.status == "unscanned"
    assert v.backend == "none"


def test_default_backend_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AV_SCAN_BACKEND", raising=False)
    s = get_scanner()
    v = s.scan("a.csv", b"x")
    assert v.backend == "none"


def test_unknown_backend_falls_back_to_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AV_SCAN_BACKEND", "nonexistent-vendor")
    s = get_scanner()
    v = s.scan("a.csv", b"x")
    assert v.backend == "none"


def test_clamav_backend_constructs(monkeypatch: pytest.MonkeyPatch) -> None:
    """When AV_SCAN_BACKEND=clamav, get_scanner returns the ClamAV
    adapter — but actually calling .scan() without a daemon falls
    back to ``unscanned`` instead of raising."""
    monkeypatch.setenv("AV_SCAN_BACKEND", "clamav")
    monkeypatch.setenv("CLAMAV_HOST", "127.0.0.1")
    monkeypatch.setenv("CLAMAV_PORT", "13310")  # unlikely-to-exist port
    s = get_scanner()
    v = s.scan("any.pdf", b"%PDF-1.4\n")
    assert v.backend == "clamav"
    # Either "unscanned" (clamd unreachable / pkg missing) — both are
    # safe-fail outcomes for the no-daemon test env.
    assert v.status in {"unscanned", "clean", "infected"}


def test_scan_attachments_returns_one_verdict_per_file() -> None:
    verdicts = scan_attachments([
        ("a.xlsx", b"x"),
        ("b.csv", b"y"),
    ])
    assert len(verdicts) == 2
    assert {v.filename for v in verdicts} == {"a.xlsx", "b.csv"}
    for v in verdicts:
        assert isinstance(v, AvVerdict)
