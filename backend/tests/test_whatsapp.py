"""WhatsApp helper tests (pure, no network)."""

from __future__ import annotations

import pytest

from app.services.whatsapp import (
    WhatsAppError,
    normalize_phone,
    parse_inbound,
    verify_webhook_challenge,
)


@pytest.mark.unit
def test_normalize_phone_accepts_trunked_tr():
    assert normalize_phone("0555 111 22 33") == "+905551112233"
    assert normalize_phone("+90 555 111 22 33") == "+905551112233"


@pytest.mark.unit
def test_normalize_phone_rejects_garbage():
    with pytest.raises(WhatsAppError):
        normalize_phone("")
    with pytest.raises(WhatsAppError):
        normalize_phone("abc")


@pytest.mark.unit
def test_parse_inbound_extracts_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.abc",
                                    "from": "905551112233",
                                    "type": "text",
                                    "text": {"body": "Merhaba"},
                                    "timestamp": "1700000000",
                                }
                            ]
                        },
                    }
                ]
            }
        ]
    }
    rows = parse_inbound(payload)
    assert len(rows) == 1
    assert rows[0]["phone_number"] == "+905551112233"
    assert rows[0]["text"] == "Merhaba"
    assert rows[0]["wa_message_id"] == "wamid.abc"


@pytest.mark.unit
def test_parse_inbound_ignores_non_message_change():
    payload = {"entry": [{"changes": [{"field": "status", "value": {}}]}]}
    assert parse_inbound(payload) == []


@pytest.mark.unit
def test_verify_webhook_rejects_wrong_token(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "secret")
    assert verify_webhook_challenge("subscribe", "wrong", "abc") is None
    assert verify_webhook_challenge("subscribe", "secret", "abc") == "abc"
    assert verify_webhook_challenge("unsubscribe", "secret", "abc") is None
