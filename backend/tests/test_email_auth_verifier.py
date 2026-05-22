"""Round-17 SPF/DKIM/DMARC verifier unit tests."""

from __future__ import annotations

import pytest

from app.services.email_auth_verifier import is_trusted, resolve_sender_auth


def _msg_with_auth_header(header_value: str) -> bytes:
    """Build a minimal raw RFC822 message with the given AR header."""
    return (
        f"From: customer@example.com\r\n"
        f"To: sales@honeywell.example\r\n"
        f"Subject: RFQ\r\n"
        f"Authentication-Results: {header_value}\r\n"
        f"\r\n"
        f"Test body\r\n"
    ).encode()


def test_dmarc_pass_is_pass() -> None:
    raw = _msg_with_auth_header("relay.example; dmarc=pass header.from=example.com")
    assert resolve_sender_auth(raw) == "pass"


def test_dmarc_fail_is_fail() -> None:
    raw = _msg_with_auth_header("relay.example; dmarc=fail header.from=example.com")
    assert resolve_sender_auth(raw) == "fail"


def test_spf_and_dkim_pass_is_pass() -> None:
    raw = _msg_with_auth_header(
        "relay.example; spf=pass smtp.mailfrom=a@b.com; dkim=pass header.d=b.com"
    )
    assert resolve_sender_auth(raw) == "pass"


def test_spf_pass_dkim_missing_is_none() -> None:
    raw = _msg_with_auth_header("relay.example; spf=pass smtp.mailfrom=a@b.com")
    # Without a DMARC verdict and without a complete pair, we
    # treat it as inconclusive.
    assert resolve_sender_auth(raw) == "none"


def test_spf_fail_is_fail() -> None:
    raw = _msg_with_auth_header("relay.example; spf=fail smtp.mailfrom=a@b.com")
    assert resolve_sender_auth(raw) == "fail"


def test_no_auth_header_is_none() -> None:
    raw = b"From: a@b.com\r\nTo: c@d.com\r\nSubject: x\r\n\r\nbody\r\n"
    assert resolve_sender_auth(raw) == "none"


def test_empty_bytes_is_none() -> None:
    assert resolve_sender_auth(b"") == "none"


def test_softfail_is_inconclusive() -> None:
    raw = _msg_with_auth_header("relay.example; spf=softfail; dkim=none")
    assert resolve_sender_auth(raw) == "none"


def test_multi_line_auth_header() -> None:
    """Some upstream gateways fold long AR headers across lines."""
    raw = (
        b"From: a@b.com\r\n"
        b"Authentication-Results: relay.example;\r\n"
        b"  dmarc=pass header.from=b.com;\r\n"
        b"  spf=pass smtp.mailfrom=a@b.com;\r\n"
        b"  dkim=pass header.d=b.com\r\n"
        b"\r\n"
        b"body\r\n"
    )
    assert resolve_sender_auth(raw) == "pass"


def test_is_trusted_predicate() -> None:
    assert is_trusted("pass") is True
    assert is_trusted("fail") is False
    assert is_trusted("none") is False
    assert is_trusted("unverified") is False
