"""Round-18 thread-aware context unit tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.email_request import EmailRequest
from app.services.email_thread_context import (
    _strip_reply_prefix,
    build_thread_prompt_block,
    fetch_thread_history,
    prepend_thread_context,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Re: hi", "hi"),
        ("FW: nested", "nested"),
        ("RE: re: FWD: deep", "deep"),
        ("YT: turkish", "turkish"),
        ("plain subject", "plain subject"),
        ("", ""),
    ],
)
def test_strip_reply_prefix(raw: str, expected: str) -> None:
    assert _strip_reply_prefix(raw) == expected


def test_build_block_empty_history_returns_empty_string() -> None:
    assert build_thread_prompt_block([]) == ""


def test_build_block_renders_parts_summary() -> None:
    prior = EmailRequest(
        id=99,
        message_id="prior",
        from_address="customer@example.com",
        subject="Acil parca",
        received_at=datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc),
        body_text="Lütfen 5 adet C7061A1012 gönderin.",
        parsed_data=json.dumps(
            {
                "parts": [
                    {"part_code": "C7061A1012", "quantity": 5},
                    {"part_code": "RM7895A1014", "quantity": 2},
                ]
            }
        ),
    )
    block = build_thread_prompt_block([prior])
    assert "Previous correspondence" in block
    assert "customer@example.com" in block
    assert "Acil parca" in block
    assert "C7061A1012" in block
    assert "RM7895A1014" in block


def test_build_block_truncates_long_bodies() -> None:
    huge = "X" * 5000
    prior = EmailRequest(
        id=1,
        message_id="big",
        from_address="a@b.com",
        subject="huge",
        received_at=datetime.now(timezone.utc),
        body_text=huge,
        parsed_data=None,
    )
    block = build_thread_prompt_block([prior])
    # Excerpt char cap is enforced — block must be much smaller than
    # the raw body size.
    assert len(block) < 2000


@pytest.mark.asyncio
async def test_fetch_thread_history_filters_by_thread_id(db, admin_user) -> None:
    now = datetime.now(timezone.utc)
    a = EmailRequest(
        tenant_id=admin_user.tenant_id,
        message_id="t-a",
        from_address="x@y.com",
        subject="RFQ",
        thread_id="thread-1",
        received_at=now - timedelta(hours=2),
        body_text="C7061A1012 5 adet",
    )
    b = EmailRequest(
        tenant_id=admin_user.tenant_id,
        message_id="t-b",
        from_address="x@y.com",
        subject="Re: RFQ",
        thread_id="thread-1",
        received_at=now - timedelta(hours=1),
        body_text="One more",
    )
    other = EmailRequest(
        tenant_id=admin_user.tenant_id,
        message_id="t-other",
        from_address="x@y.com",
        subject="Different",
        thread_id="thread-other",
        received_at=now - timedelta(minutes=30),
        body_text="unrelated",
    )
    db.add_all([a, b, other])
    await db.commit()
    for row in (a, b, other):
        await db.refresh(row)

    # Pretend a third mail in the same thread came in just now.
    current = EmailRequest(
        id=999_999,
        tenant_id=admin_user.tenant_id,
        message_id="current",
        from_address="x@y.com",
        subject="Re: Re: RFQ",
        thread_id="thread-1",
        received_at=now,
    )
    history = await fetch_thread_history(db, current)
    history_ids = {e.id for e in history}
    assert a.id in history_ids
    assert b.id in history_ids
    assert other.id not in history_ids


@pytest.mark.asyncio
async def test_fetch_thread_history_tenant_scoped(db, admin_user) -> None:
    other_tenant = EmailRequest(
        tenant_id=999,  # different tenant
        message_id="cross-tenant",
        from_address="x@y.com",
        thread_id="t-cross",
        received_at=datetime.now(timezone.utc),
        body_text="cross",
    )
    db.add(other_tenant)
    await db.commit()

    current = EmailRequest(
        id=999_998,
        tenant_id=admin_user.tenant_id,
        message_id="current-cross",
        from_address="x@y.com",
        thread_id="t-cross",
        received_at=datetime.now(timezone.utc),
    )
    history = await fetch_thread_history(db, current)
    # Cross-tenant row must NOT appear.
    assert all(e.tenant_id == admin_user.tenant_id for e in history)


@pytest.mark.asyncio
async def test_prepend_thread_context_returns_body_when_no_history(db, admin_user) -> None:
    current = EmailRequest(
        id=999_997,
        tenant_id=admin_user.tenant_id,
        message_id="no-history",
        from_address="brand-new@example.com",
        thread_id=None,
        subject="Brand new conversation",
        received_at=datetime.now(timezone.utc),
    )
    out = await prepend_thread_context(db, current, "Body content here.")
    assert out == "Body content here."
