"""Cockpit risky accounts endpoint tests."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.user import User
from app.services.customer_health_service import CustomerHealthReport


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        tenant_id=_TENANT_ID,
        email="cockpit_risky_mgr@test.com",
        full_name="Cockpit Risky Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_risky_accounts_enriched(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)

    cust = Customer(tenant_id=_TENANT_ID, name="Acme", email="acme_cockpit_risky@test.com", company="Acme AŞ")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="Acme Deal",
        stage="qualified",
        status="active",
        owner_id=user.id,
        customer_id=cust.id,
        amount=5000,
        currency="TRY",
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    sig = OpportunitySignal(
        opportunity_id=opp.id,
        signal_type="test",
        severity="high",
        evidence="x",
        source_type="test",
        source_id=1,
        is_resolved=False,
    )
    db.add(sig)
    await db.commit()

    report = CustomerHealthReport(
        customer_id=cust.id,
        customer_name=cust.name,
        company=cust.company,
        score=35,
        risk_level="at_risk",
    )

    with patch("app.api.v1.cockpit.settings") as ms, patch(
        "app.api.v1.cockpit.CustomerHealthService"
    ) as svc_cls:
        ms.FEATURE_REVENUE_COCKPIT = True
        inst = AsyncMock()
        inst.get_at_risk_customers = AsyncMock(return_value=[report])
        svc_cls.return_value = inst

        r = await client.get("/api/v1/cockpit/risky-accounts", headers=h)
        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] == 1
        row = payload["items"][0]
        assert row["customer_id"] == cust.id
        assert row["active_opportunities"] == 1
        assert row["pipeline_total"] == 5000.0
        assert row["unresolved_high_signals"] == 1
