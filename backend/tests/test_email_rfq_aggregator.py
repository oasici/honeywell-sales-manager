"""Round-18 multi-email RFQ aggregation tests."""

from __future__ import annotations

import json

import pytest

from app.models.email_request import EmailRequest
from app.services.email_rfq_aggregator import (
    _normalise_subject,
    _sender_domain,
    aggregate_parts,
    compute_rfq_thread_key,
    link_email_to_rfq,
    list_emails_in_rfq,
)


# ── Subject normalisation ─────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Re: hello", "hello"),
        ("Fwd: RFQ", "rfq"),
        ("RE: re: re: nested", "nested"),
        ("YT: Türkçe ön ek", "türkçe ön ek"),
        ("İletme: forwarded mail", "forwarded mail"),
        ("  Some  multispaced ", "some multispaced"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalise_subject(raw: str | None, expected: str) -> None:
    assert _normalise_subject(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a@b.com", "b.com"),
        ("A@B.COM", "b.com"),
        ("nodomain", "nodomain"),
        (None, ""),
        ("", ""),
    ],
)
def test_sender_domain(raw: str | None, expected: str) -> None:
    assert _sender_domain(raw) == expected


# ── Thread key stability ──────────────────────────────────────────


def test_same_thread_id_produces_same_key() -> None:
    e1 = EmailRequest(
        tenant_id=1,
        thread_id="abc123",
        from_address="a@b.com",
        subject="anything",
    )
    e2 = EmailRequest(
        tenant_id=1,
        thread_id="abc123",
        from_address="different@d.com",
        subject="totally other",
    )
    assert compute_rfq_thread_key(e1) == compute_rfq_thread_key(e2)


def test_different_tenants_get_different_keys() -> None:
    e1 = EmailRequest(tenant_id=1, thread_id="same", from_address="a@b.com")
    e2 = EmailRequest(tenant_id=2, thread_id="same", from_address="a@b.com")
    assert compute_rfq_thread_key(e1) != compute_rfq_thread_key(e2)


def test_no_thread_id_uses_sender_subject_fallback() -> None:
    e1 = EmailRequest(
        tenant_id=1,
        thread_id=None,
        from_address="ahmet@abc.com",
        subject="RFQ ekte",
    )
    e2 = EmailRequest(
        tenant_id=1,
        thread_id=None,
        from_address="ahmet@abc.com",
        subject="Re: RFQ ekte",
    )
    e3 = EmailRequest(
        tenant_id=1,
        thread_id=None,
        from_address="ahmet@abc.com",
        subject="Different subject",
    )
    # 1 and 2 share the same normalised subject + domain → same RFQ.
    assert compute_rfq_thread_key(e1) == compute_rfq_thread_key(e2)
    # 3 has a different normalised subject → different RFQ.
    assert compute_rfq_thread_key(e1) != compute_rfq_thread_key(e3)


# ── Aggregation ───────────────────────────────────────────────────


def _email_with_parts(parts: list[dict], email_id: int = 1) -> EmailRequest:
    e = EmailRequest(
        id=email_id,
        tenant_id=1,
        from_address="a@b.com",
        subject="RFQ",
        message_id=f"m{email_id}",
        parsed_data=json.dumps({"parts": parts, "confidence": 0.9}),
    )
    return e


def test_aggregate_sums_quantities_by_code() -> None:
    e1 = _email_with_parts([{"part_code": "C7061A1012", "quantity": 5}], email_id=1)
    e2 = _email_with_parts([{"part_code": "C7061A1012", "quantity": 3}], email_id=2)
    agg = aggregate_parts([e1, e2])
    assert len(agg) == 1
    assert agg[0]["part_code"] == "C7061A1012"
    assert agg[0]["quantity"] == 8
    assert sorted(agg[0]["source_email_ids"]) == [1, 2]


def test_aggregate_case_insensitive_code_dedup() -> None:
    e1 = _email_with_parts([{"part_code": "C7061A1012", "quantity": 5}], email_id=1)
    e2 = _email_with_parts([{"part_code": "c7061a1012", "quantity": 2}], email_id=2)
    agg = aggregate_parts([e1, e2])
    assert len(agg) == 1
    assert agg[0]["quantity"] == 7


def test_aggregate_keeps_description_only_separate() -> None:
    e1 = _email_with_parts(
        [{"part_code": "", "part_description": "flame detector"}], email_id=1
    )
    e2 = _email_with_parts(
        [{"part_code": "", "part_description": "pressure transmitter"}], email_id=2
    )
    agg = aggregate_parts([e1, e2])
    assert len(agg) == 2


def test_aggregate_handles_invalid_parsed_data() -> None:
    e = EmailRequest(
        id=1,
        tenant_id=1,
        message_id="m1",
        from_address="a@b.com",
        parsed_data="not json",
    )
    agg = aggregate_parts([e])
    assert agg == []


# ── DB integration ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_link_email_to_rfq_persists_key(db, admin_user) -> None:
    email = EmailRequest(
        tenant_id=admin_user.tenant_id,
        message_id="m-link-1",
        from_address="customer@example.com",
        subject="Acil parca",
        thread_id="t-1",
        body_text="C7061A1012 5 adet",
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    key = await link_email_to_rfq(db, email)
    assert key is not None
    assert email.rfq_thread_key == key

    # Idempotent — second call returns the same key, no error.
    same = await link_email_to_rfq(db, email)
    assert same == key


@pytest.mark.asyncio
async def test_list_emails_in_rfq_tenant_scoped(db, admin_user) -> None:
    e1 = EmailRequest(
        tenant_id=admin_user.tenant_id,
        message_id="rfq-list-1",
        from_address="customer@example.com",
        subject="RFQ",
        thread_id="shared-thread",
    )
    e2 = EmailRequest(
        tenant_id=admin_user.tenant_id,
        message_id="rfq-list-2",
        from_address="customer@example.com",
        subject="Re: RFQ",
        thread_id="shared-thread",
    )
    db.add_all([e1, e2])
    await db.commit()

    await link_email_to_rfq(db, e1)
    await link_email_to_rfq(db, e2)

    assert e1.rfq_thread_key == e2.rfq_thread_key
    found = await list_emails_in_rfq(
        db, e1.rfq_thread_key, tenant_id=admin_user.tenant_id
    )
    found_ids = {e.id for e in found}
    assert e1.id in found_ids and e2.id in found_ids
