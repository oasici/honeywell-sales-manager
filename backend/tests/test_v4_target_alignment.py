from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal
from app.models.revenue_signal import RevenueSignal
from app.models.user import User


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _user(db: AsyncSession, email: str, role: str) -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email=email,
        full_name="T",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(u: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


@pytest.mark.asyncio
async def test_alignment_timeline_flag_off_returns_404(client: AsyncClient, db: AsyncSession):
    mgr = await _user(db, "align_off@test.com", "sales_manager")
    r = await client.get("/api/v1/v4/alignment/opportunities/1/normalized-timeline", headers=_auth(mgr))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_alignment_timeline_merges_sources(client: AsyncClient, db: AsyncSession):
    with patch("app.api.v1.target_alignment.settings") as s:
        s.FEATURE_V4_ADDITIVE_READMODEL = True
        mgr = await _user(db, "align_on@test.com", "sales_manager")
        cust = Customer(tenant_id=_TENANT_ID, name="C", company="C", email="c@test.com", phone="", address="", tax_id="")
        db.add(cust)
        await db.commit()
        await db.refresh(cust)

        opp = Opportunity(
            tenant_id=_TENANT_ID,
            customer_id=cust.id,
            owner_id=mgr.id,
            title="O",
            stage="qualified",
            status="active",
            amount=1,
            currency="TRY",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            updated_at=datetime.now(timezone.utc),
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
                summary="hello",
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        db.add(
            OpportunityEvent(
                tenant_id=opp.tenant_id,
                opportunity_id=opp.id,
                event_type="email",
                entity_type="email",
                entity_id=1,
                description="sent",
                occurred_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        db.add(
            RevenueSignal(
                signal_type="no_touch",
                source_entity_type="test",
                source_entity_id=None,
                opportunity_id=opp.id,
                customer_id=cust.id,
                owner_id=mgr.id,
                severity="med",
                confidence=0.55,
                recommended_action="Follow up",
                metadata_json='{"model_version":"v4-mvp","value":"no_touch"}',
            )
        )
        db.add(
            OpportunitySignal(
                tenant_id=opp.tenant_id,
                opportunity_id=opp.id,
                signal_type="pricing_concern",
                severity="high",
                evidence="too expensive",
                source_type="email",
                source_id=99,
                is_resolved=False,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            )
        )
        await db.commit()

        r = await client.get(
            f"/api/v1/v4/alignment/opportunities/{opp.id}/normalized-timeline",
            headers=_auth(mgr),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert body["include_signals"] is True
        kinds = {i["provenance"] for i in body["items"]}
        assert kinds == {"activity_logs", "opportunity_events", "revenue_signals"}

        r2 = await client.get(
            f"/api/v1/v4/alignment/opportunities/{opp.id}/normalized-timeline?include_signals=false",
            headers=_auth(mgr),
        )
        assert r2.status_code == 200
        assert r2.json()["total"] == 2

        r3 = await client.get(
            f"/api/v1/v4/alignment/opportunities/{opp.id}/normalized-timeline"
            "?include_legacy_opportunity_signals=true",
            headers=_auth(mgr),
        )
        assert r3.status_code == 200
        assert r3.json()["total"] == 4
        prov = {i["provenance"] for i in r3.json()["items"]}
        assert prov == {"activity_logs", "opportunity_events", "revenue_signals", "opportunity_signals"}

        cs = await client.get(
            f"/api/v1/v4/alignment/opportunities/{opp.id}/conversation-signals",
            headers=_auth(mgr),
        )
        assert cs.status_code == 200
        cbody = cs.json()
        assert cbody["total"] == 2
        feeds = {i["feed"] for i in cbody["items"]}
        assert feeds == {"revenue_signals", "opportunity_signals"}
        by_feed = {i["feed"]: i for i in cbody["items"]}
        assert by_feed["revenue_signals"]["signal_type"] == "no_touch"
        assert by_feed["opportunity_signals"]["signal_type"] == "pricing_concern"
        assert by_feed["opportunity_signals"]["model_version"] == "legacy-opportunity-signals"

        cs2 = await client.get(
            f"/api/v1/v4/alignment/opportunities/{opp.id}/conversation-signals"
            "?include_legacy_opportunity_signals=false",
            headers=_auth(mgr),
        )
        assert cs2.status_code == 200
        assert cs2.json()["total"] == 1
