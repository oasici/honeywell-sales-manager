from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.deal_replay_snapshot import DealReplaySnapshot
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.sales_dna_snapshot import SalesDnaSnapshot
from app.models.user import User
from app.services.v4_learning_nightly import collect_active_opportunity_ids, run_v4_deal_replay_nightly, run_v4_sales_dna_nightly


async def _mgr(db: AsyncSession) -> User:
    u = User(
        email="learn_nightly@test.com",
        full_name="M",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_collect_active_opportunity_ids_union(db: AsyncSession):
    mgr = await _mgr(db)
    cust = Customer(name="LC", company="LC", email="lc@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    snap = date(2026, 3, 15)
    opp = Opportunity(
        customer_id=cust.id,
        owner_id=mgr.id,
        title="Learn",
        stage="qualified",
        status="active",
        amount=1,
        currency="TRY",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    end = datetime.combine(snap, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=12)
    db.add(
        ActivityLog(
            activity_type="note_added",
            entity_type="opportunity",
            entity_id=opp.id,
            opportunity_id=opp.id,
            customer_id=cust.id,
            user_id=mgr.id,
            summary="x",
            created_at=end,
        )
    )
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=snap,
            deal_age_days=1,
            days_since_last_rep_touch=1,
            days_since_last_buyer_touch=1,
            rep_touch_count_14d=1,
            buyer_reply_count_14d=0,
            meeting_count_30d=0,
            quote_count=0,
            competitor_mentions_30d=0,
            pricing_objections_30d=0,
            positive_signal_count_14d=0,
            negative_signal_count_14d=0,
        )
    )
    await db.commit()

    ids = await collect_active_opportunity_ids(db, snap, limit=50)
    assert opp.id in ids


@pytest.mark.asyncio
async def test_run_sales_dna_and_replay_nightly(db: AsyncSession):
    mgr = await _mgr(db)
    cust = Customer(name="LR", company="LR", email="lr@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    snap = date(2026, 3, 20)
    opp = Opportunity(
        customer_id=cust.id,
        owner_id=mgr.id,
        title="N2",
        stage="qualified",
        status="active",
        amount=1,
        currency="TRY",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    ts = datetime.combine(snap, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1, hours=-2)
    db.add(
        ActivityLog(
            activity_type="note_added",
            entity_type="opportunity",
            entity_id=opp.id,
            opportunity_id=opp.id,
            customer_id=cust.id,
            user_id=mgr.id,
            summary="n",
            created_at=ts,
        )
    )
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=snap,
            deal_age_days=2,
            days_since_last_rep_touch=2,
            days_since_last_buyer_touch=2,
            rep_touch_count_14d=1,
            buyer_reply_count_14d=0,
            meeting_count_30d=0,
            quote_count=0,
            competitor_mentions_30d=0,
            pricing_objections_30d=0,
            positive_signal_count_14d=0,
            negative_signal_count_14d=0,
        )
    )
    await db.commit()

    with patch("app.services.v4_learning_nightly.settings") as s:
        s.V4_SALES_DNA_NIGHTLY_MAX_OPPORTUNITIES = 50
        s.V4_DEAL_REPLAY_NIGHTLY_MAX_OPPORTUNITIES = 50
        dna_r = await run_v4_sales_dna_nightly(db, target_date=snap)
        assert dna_r["processed"] >= 1

    row = (
        await db.execute(
            select(SalesDnaSnapshot).where(
                SalesDnaSnapshot.opportunity_id == opp.id,
                SalesDnaSnapshot.snapshot_date == snap,
            )
        )
    ).scalar_one_or_none()
    assert row is not None

    with patch("app.services.v4_learning_nightly.settings") as s:
        s.V4_SALES_DNA_NIGHTLY_MAX_OPPORTUNITIES = 50
        s.V4_DEAL_REPLAY_NIGHTLY_MAX_OPPORTUNITIES = 50
        rep_r = await run_v4_deal_replay_nightly(db, target_date=snap)
        assert rep_r["processed"] >= 1

    r2 = (
        await db.execute(
            select(DealReplaySnapshot).where(
                DealReplaySnapshot.opportunity_id == opp.id,
                DealReplaySnapshot.snapshot_date == snap,
            )
        )
    ).scalar_one_or_none()
    assert r2 is not None
