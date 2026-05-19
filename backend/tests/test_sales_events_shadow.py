from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal
from app.models.revenue_signal import RevenueSignal
from app.models.sales_event_shadow import SalesEventShadow
from app.models.user import User
from app.services.sales_events_shadow_sync import sync_sales_events_shadow_window


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _mgr(db: AsyncSession) -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email="shadow_mgr@test.com",
        full_name="M",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(u: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


@pytest.mark.asyncio
async def test_shadow_sync_idempotent_and_api(client: AsyncClient, db: AsyncSession):
    mgr = await _mgr(db)
    cust = Customer(tenant_id=_TENANT_ID, name="S", company="S", email="s@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    now = datetime.now(timezone.utc)
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=mgr.id,
        title="Sh",
        stage="qualified",
        status="active",
        amount=1,
        currency="TRY",
        created_at=now - timedelta(days=1),
        updated_at=now,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    db.add(
        ActivityLog(
            activity_type="note_added",
            entity_type="opportunity",
            entity_id=opp.id,
            opportunity_id=opp.id,
            customer_id=cust.id,
            user_id=mgr.id,
            summary="n",
            created_at=now - timedelta(hours=5),
        )
    )
    db.add(
        OpportunityEvent(
            tenant_id=opp.tenant_id,
            opportunity_id=opp.id,
            event_type="email",
            entity_type="email",
            entity_id=1,
            description="e",
            occurred_at=now - timedelta(hours=4),
        )
    )
    db.add(
        RevenueSignal(
            signal_type="positive",
            source_entity_type="t",
            source_entity_id=None,
            opportunity_id=opp.id,
            customer_id=cust.id,
            owner_id=mgr.id,
            severity="low",
            confidence=0.9,
            metadata_json="{}",
            created_at=now - timedelta(hours=3),
        )
    )
    db.add(
        OpportunitySignal(
            tenant_id=opp.tenant_id,
            opportunity_id=opp.id,
            signal_type="objection",
            severity="med",
            evidence="legacy",
            source_type="ai",
            source_id=1,
            is_resolved=False,
            created_at=now - timedelta(hours=2),
        )
    )
    await db.commit()

    win_start = now - timedelta(days=1)
    win_end = now + timedelta(days=1)
    c1 = await sync_sales_events_shadow_window(db, window_start=win_start, window_end=win_end)
    assert (
        c1["activity_logs"] + c1["opportunity_events"] + c1["revenue_signals"] + c1["opportunity_signals"]
        == 4
    )

    c2 = await sync_sales_events_shadow_window(db, window_start=win_start, window_end=win_end)
    assert c2["skipped"] == 4

    n = (
        await db.execute(
            select(func.count(SalesEventShadow.id)).where(SalesEventShadow.opportunity_id == opp.id)
        )
    ).scalar_one()
    assert int(n) == 4

    with patch("app.api.v1.target_alignment.settings") as s:
        s.FEATURE_V4_SALES_EVENTS_SHADOW = True
        r = await client.get(
            f"/api/v1/v4/alignment/opportunities/{opp.id}/shadow-timeline",
            headers=_auth(mgr),
        )
    assert r.status_code == 200
    assert r.json()["total"] == 4


async def _rep(db: AsyncSession) -> User:
    u = User(
        email="shadow_rep@test.com",
        full_name="R",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _ops(db: AsyncSession) -> User:
    u = User(
        email="shadow_ops@test.com",
        full_name="Ops",
        hashed_password=hash_password("Test1234"),
        role="operations",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_shadow_manual_post_backfill_manager(client: AsyncClient, db: AsyncSession):
    mgr = await _mgr(db)
    with patch("app.api.v1.target_alignment.settings") as s:
        s.FEATURE_V4_SALES_EVENTS_SHADOW = True
        r = await client.post(
            "/api/v1/v4/alignment/shadow/sync-window",
            json={"days": 1},
            headers=_auth(mgr),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["window_days"] == 1
    assert "counts" in body


@pytest.mark.asyncio
async def test_shadow_manual_post_forbidden_for_rep(client: AsyncClient, db: AsyncSession):
    rep = await _rep(db)
    with patch("app.api.v1.target_alignment.settings") as s:
        s.FEATURE_V4_SALES_EVENTS_SHADOW = True
        r = await client.post(
            "/api/v1/v4/alignment/shadow/sync-window",
            json={"days": 1},
            headers=_auth(rep),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_shadow_manual_post_backfill_operations(client: AsyncClient, db: AsyncSession):
    ops = await _ops(db)
    with patch("app.api.v1.target_alignment.settings") as s:
        s.FEATURE_V4_SALES_EVENTS_SHADOW = True
        r = await client.post(
            "/api/v1/v4/alignment/shadow/sync-window",
            json={"days": 2},
            headers=_auth(ops),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["window_days"] == 2
    assert "counts" in body
