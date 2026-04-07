"""C3: Customer health explainability tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.user import User


async def _setup(db: AsyncSession):
    user = User(
        email="health_test@test.com",
        full_name="Health Tester",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    customer = Customer(
        name="Test Corp",
        company="Test Corp Ltd",
        email="test@corp.com",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(user)
    await db.refresh(customer)
    return user, customer


@pytest.mark.asyncio
async def test_health_endpoint_returns_200_with_empty_data(client: AsyncClient, db: AsyncSession):
    user, customer = await _setup(db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get(
        f"/api/v1/customers/health/{customer.id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "indicators" in data
    assert isinstance(data["indicators"], list)


@pytest.mark.asyncio
async def test_health_explain_returns_explanations(client: AsyncClient, db: AsyncSession):
    user, customer = await _setup(db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get(
        f"/api/v1/customers/health/{customer.id}?explain=true",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "explanations" in data
    assert isinstance(data["explanations"], list)
    assert len(data["explanations"]) > 0

    # Each explanation should have required fields
    for exp in data["explanations"]:
        assert "indicator" in exp
        assert "weight" in exp
        assert "contribution" in exp


@pytest.mark.asyncio
async def test_health_without_explain_has_no_explanations(client: AsyncClient, db: AsyncSession):
    user, customer = await _setup(db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get(
        f"/api/v1/customers/health/{customer.id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "explanations" not in data


@pytest.mark.asyncio
async def test_health_contributions_sum_approximately_to_score(client: AsyncClient, db: AsyncSession):
    user, customer = await _setup(db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get(
        f"/api/v1/customers/health/{customer.id}?explain=true",
        headers=headers,
    )
    data = response.json()
    if data.get("explanations"):
        contribution_sum = sum(e["contribution"] for e in data["explanations"])
        # Score and contribution sum should be close (within rounding tolerance)
        assert abs(data["score"] - contribution_sum) < 5, (
            f"Score {data['score']} vs contribution sum {contribution_sum}"
        )
