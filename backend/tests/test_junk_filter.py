"""Junk / bulk sender filter tests (pre-LLM drop).

Catches the real-inbox junk (Apple receipts, CNN/Fanatik news, promos,
no-reply/testflight) without touching a real human RFQ.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.junk_filter import is_bulk_headers, is_junk_email


class TestNoReplySenders:
    @pytest.mark.parametrize(
        "addr",
        [
            "no_reply@email.apple.com",
            "noreply@example.com",
            "no-reply@news.site",
            "testflight_no_reply@email.apple.com",  # token mid-localpart
            "mailer-daemon@host",
            "postmaster@host",
            "donotreply@bank.com",
        ],
    )
    def test_noreply_localparts_are_junk(self, addr):
        junk, reason = is_junk_email(addr)
        assert junk is True
        assert reason == "noreply_sender"


class TestBulkHeaders:
    def test_list_unsubscribe_is_bulk(self):
        assert is_bulk_headers(list_unsubscribe="<mailto:u@x.com>") is True

    def test_precedence_bulk_is_bulk(self):
        assert is_bulk_headers(precedence="bulk") is True

    def test_auto_submitted_is_bulk(self):
        assert is_bulk_headers(auto_submitted="auto-generated") is True

    def test_auto_submitted_no_is_not_bulk(self):
        assert is_bulk_headers(auto_submitted="no") is False

    def test_plain_headers_not_bulk(self):
        assert is_bulk_headers() is False

    def test_bulk_email_flagged_junk(self):
        # a promo from a real-looking sender is junk purely on headers
        junk, reason = is_junk_email("hello@timeleft.com", is_bulk=True)
        assert junk is True and reason == "bulk_mail"


class TestRealSendersPass:
    @pytest.mark.parametrize(
        "addr",
        [
            "birkanege.durukan@tanap.com",
            "neslihan.halat@tanap.com",
            "procurement@customer.com",
            "ahmet.yilmaz@abc-endustri.com.tr",
        ],
    )
    def test_human_rfq_senders_pass(self, addr):
        junk, reason = is_junk_email(addr, is_bulk=False)
        assert junk is False and reason is None


class TestConfigToggles:
    def test_disabled_filter_passes_everything(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_JUNK_FILTER_ENABLED", False)
        assert is_junk_email("no_reply@apple.com", is_bulk=True) == (False, None)

    def test_custom_pattern_matches(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_JUNK_SENDER_PATTERNS", "fanatik.com,cnnturk")
        junk, reason = is_junk_email("bulten@fanatik.com")
        assert junk is True and reason == "junk_sender"
