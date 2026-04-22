"""Tests for the PII scrubber / AI Trust Layer."""

from __future__ import annotations

import pytest

from app.services.ai_trust import AITrustContext, audit_record, scrub, scrub_many, unscrub


@pytest.mark.unit
def test_scrub_masks_email_and_phone():
    text = "Müşteri: ayse.kaya@example.com  Tel: +90 212 555 12 34"
    masked, ctx = scrub(text)

    assert "ayse.kaya@example.com" not in masked
    assert "+90 212 555 12 34" not in masked
    assert "<<EMAIL_" in masked
    assert "<<PHONE_" in masked
    assert ctx.hit_counts["EMAIL"] == 1
    assert ctx.hit_counts["PHONE"] == 1


@pytest.mark.unit
def test_scrub_is_deterministic_per_context():
    raw = "Mail: a@b.com, tekrar a@b.com"
    masked, ctx = scrub(raw)
    assert masked.count("<<EMAIL_") == 2
    # Same raw value resolves to the same token within one ctx.
    tokens = [tok for tok in ctx.token_map.values() if tok.startswith("<<EMAIL_")]
    assert len(set(tokens)) == 1


@pytest.mark.unit
def test_unscrub_restores_original():
    raw = "VKN: 1234567890  Mail: x@y.com"
    masked, ctx = scrub(raw)
    assert "<<" in masked
    restored = unscrub(masked, ctx)
    assert restored == raw


@pytest.mark.unit
def test_scrub_many_shares_context():
    payloads = {"subject": "Mail: a@b.com", "body": "Tekrar a@b.com ve 05551112233"}
    cleaned, ctx = scrub_many(payloads)
    email_token = [t for t in ctx.token_map.values() if t.startswith("<<EMAIL_")][0]
    assert cleaned["subject"].count(email_token) == 1
    assert cleaned["body"].count(email_token) == 1
    assert "PHONE" in ctx.hit_counts


@pytest.mark.unit
def test_tckn_detected_when_11_digits():
    masked, ctx = scrub("TCKN 12345678901")
    assert "<<TCKN_" in masked
    assert ctx.hit_counts.get("TCKN") == 1


@pytest.mark.unit
def test_iban_masked():
    masked, ctx = scrub("IBAN TR33 0006 1005 1978 6457 8413 26")
    assert "TR33" not in masked
    assert ctx.hit_counts["IBAN"] == 1


@pytest.mark.unit
def test_audit_record_hides_raw_prompt():
    prompt = "My VKN is 1234567890"
    _, ctx = scrub(prompt)
    record = audit_record(ctx, prompt=prompt, model="claude-sonnet-4")
    assert record["model"] == "claude-sonnet-4"
    assert record["pii_hits"].get("VKN") == 1
    assert len(record["prompt_sha256"]) == 64
    assert "1234567890" not in record["prompt_sha256"]


@pytest.mark.unit
def test_empty_input_noop():
    masked, ctx = scrub("")
    assert masked == ""
    assert not ctx.is_dirty()
