"""Tests for ERP mapping engine + conflict helpers."""

from __future__ import annotations

import pytest

from app.services.erp.mapping_engine import (
    compute_payload_hash,
    diff_payloads,
    normalize_turkish,
    to_internal_customer,
    to_internal_product,
)


@pytest.mark.unit
def test_normalize_strips_nbsp_and_curly_quote():
    assert normalize_turkish("Acme\u00a0Ltd\u2019") == "Acme Ltd'"
    assert normalize_turkish(None) is None
    assert normalize_turkish("   ") is None


@pytest.mark.unit
def test_to_internal_customer_default_map():
    raw = {
        "name": "Kaya\u00a0A.\u015e.",
        "tax_number": "1234567890",
        "email": "a@b.com",
        "phone": "02125551234",
        "address": "Istanbul",
        "city": "Istanbul",
    }
    out = to_internal_customer(raw)
    assert out["name"] == "Kaya A.\u015e."
    assert out["tax_number"] == "1234567890"
    assert out["email"] == "a@b.com"


@pytest.mark.unit
def test_to_internal_customer_override():
    raw = {"VKN_TCKN": "123", "Definition": "Kaya"}
    cfg = '{"field_map":{"customer":{"tax_number":"VKN_TCKN","name":"Definition"}}}'
    out = to_internal_customer(raw, config_json=cfg)
    assert out["tax_number"] == "123"
    assert out["name"] == "Kaya"


@pytest.mark.unit
def test_to_internal_product_pipes_unit_price():
    raw = {"sku": "HW-42", "name": "Filter", "unit_price": 19.99, "currency": "TRY"}
    out = to_internal_product(raw)
    assert out["sku"] == "HW-42"
    assert out["unit_price"] == 19.99


@pytest.mark.unit
def test_payload_hash_deterministic():
    a = {"name": "Acme", "phone": "1"}
    b = {"phone": "1", "name": "Acme"}  # key order difference must not matter
    assert compute_payload_hash(a) == compute_payload_hash(b)
    c = {"name": "Acme", "phone": "2"}
    assert compute_payload_hash(a) != compute_payload_hash(c)


@pytest.mark.unit
def test_diff_payloads_reports_changes():
    hss = {"name": "Acme", "phone": "1", "updated_at": "x"}
    erp = {"name": "Acme Corp", "phone": "1", "updated_at": "y"}
    diffs = diff_payloads(hss, erp)
    # updated_at is ignored by default
    assert len(diffs) == 1
    assert diffs[0]["field"] == "name"
    assert diffs[0]["hss"] == "Acme"
    assert diffs[0]["erp"] == "Acme Corp"
