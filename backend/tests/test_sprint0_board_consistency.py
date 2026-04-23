import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import EmailStatus
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.user import User


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        email="s0_board_mgr@test.com",
        full_name="Sprint0 Board Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_board_kanban_items_have_probability_and_quotes_link(
    client: AsyncClient, db: AsyncSession
):
    with patch("app.api.v1.opportunities.settings") as ms:
        ms.FEATURE_V2_BOARD = True
        ms.FEATURE_GUIDED_SELLING = False

        user, h = await _mgr(db)

        # Create a minimal opportunity + a quote linked to it
        opp = Opportunity(title="Board Deal", stage="qualified", owner_id=user.id, probability=0.25)
        db.add(opp)
        await db.commit()
        await db.refresh(opp)

        quote = Quote(
            quote_number="S0-Q-001",
            status="draft",
            language="tr",
            currency="TRY",
            opportunity_id=opp.id,
        )
        db.add(quote)
        await db.commit()

        r = await client.get("/api/v1/board/kanban", headers=h)
        assert r.status_code == 200
        columns = r.json()["columns"]
        assert columns

        # Find qualified column and our opp
        qualified = next(c for c in columns if c["stage"] == "qualified")
        items = qualified["items"]
        found = next(i for i in items if i["id"] == opp.id)

        assert "probability" in found
        assert found["probability"] is not None

        # Detail endpoint must expose open_quotes_count and be >= 1
        d = await client.get(f"/api/v1/opportunities/{opp.id}", headers=h)
        assert d.status_code == 200
        assert d.json()["open_quotes_count"] >= 1

