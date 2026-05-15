import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.user import User
from app.core.security import hash_password
from app.services.predictive_scoring_service import predict_close_probability


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


@pytest.mark.asyncio
async def test_predictive_scoring_returns_probability_in_0_1(db: AsyncSession):
    user = User(
        tenant_id=_TENANT_ID,
        email="ps@test.com",
        full_name="Predictive Test",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    opp = Opportunity(tenant_id=_TENANT_ID, title="P Deal", stage="qualified", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    res = await predict_close_probability(db, opp.id)
    assert "close_probability" in res
    p = float(res["close_probability"])
    assert 0.0 <= p <= 1.0
    assert res.get("method") == "heuristic_v1_5"
    assert res.get("confidence_band") in ("low", "medium", "high")
    assert isinstance(res.get("factors"), list)

