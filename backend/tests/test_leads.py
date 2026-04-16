"""Tests for lead lifecycle — CRUD, scoring, conversion."""

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User
from app.core.security import hash_password
from app.services.lead_service import LeadService


@pytest_asyncio.fixture
async def sales_user(db: AsyncSession) -> User:
    user = User(
        email="rep@test.com",
        full_name="Sales Rep",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture(autouse=True)
def _enable_lead_lifecycle():
    with patch("app.api.v1.leads.settings") as mock_settings:
        mock_settings.FEATURE_LEAD_LIFECYCLE = True
        yield


# ── Service Tests ──

@pytest.mark.asyncio
async def test_create_lead(db: AsyncSession, sales_user: User):
    service = LeadService(db)
    lead = await service.create_lead(
        first_name="Ahmet",
        last_name="Yilmaz",
        email="ahmet@testcorp.com",
        company="Test Corp",
        phone="+905551234567",
        source="referral",
        owner_id=sales_user.id,
    )
    await db.commit()

    assert lead.id is not None
    assert lead.first_name == "Ahmet"
    assert lead.status == "new"
    assert lead.lead_score > 0  # auto-scored


@pytest.mark.asyncio
async def test_lead_scoring(db: AsyncSession, sales_user: User):
    """Lead with more info gets higher score."""
    service = LeadService(db)

    # Minimal lead
    lead_minimal = await service.create_lead(
        first_name="Min", last_name="Lead", email="min@x.com",
        source="manual", owner_id=sales_user.id,
    )

    # Rich lead
    lead_rich = await service.create_lead(
        first_name="Rich", last_name="Lead", email="rich@corp.com",
        company="BigCo", phone="+123", title="Director",
        source="referral", owner_id=sales_user.id,
    )
    await db.commit()

    assert lead_rich.lead_score > lead_minimal.lead_score


@pytest.mark.asyncio
async def test_convert_lead(db: AsyncSession, sales_user: User):
    service = LeadService(db)
    lead = await service.create_lead(
        first_name="Convert", last_name="Me", email="convert@test.com",
        company="ConvertCo", source="email", owner_id=sales_user.id,
    )
    # Must qualify first
    lead.status = "qualified"
    await db.flush()

    result = await service.convert_lead(
        lead_id=lead.id,
        user_id=sales_user.id,
        create_opportunity=True,
        opportunity_title="ConvertCo Deal",
        opportunity_amount=50000.0,
    )
    await db.commit()

    assert result["customer_id"] is not None
    assert result["opportunity_id"] is not None

    # Verify lead is converted
    updated = (await db.execute(select(Lead).where(Lead.id == lead.id))).scalar_one()
    assert updated.status == "converted"
    assert updated.converted_customer_id == result["customer_id"]


@pytest.mark.asyncio
async def test_convert_lead_without_opportunity(db: AsyncSession, sales_user: User):
    service = LeadService(db)
    lead = await service.create_lead(
        first_name="No", last_name="Opp", email="noopp@test.com",
        owner_id=sales_user.id,
    )
    lead.status = "qualified"
    await db.flush()

    result = await service.convert_lead(
        lead_id=lead.id, user_id=sales_user.id, create_opportunity=False,
    )
    await db.commit()

    assert result["customer_id"] is not None
    assert result["opportunity_id"] is None


@pytest.mark.asyncio
async def test_convert_lead_rejects_unconverted_status(db: AsyncSession, sales_user: User):
    service = LeadService(db)
    lead = await service.create_lead(
        first_name="New", last_name="Lead", email="new@test.com",
        owner_id=sales_user.id,
    )
    await db.flush()

    from app.core.exceptions import BadRequestException
    with pytest.raises(BadRequestException, match="qualified"):
        await service.convert_lead(lead.id, sales_user.id)


@pytest.mark.asyncio
async def test_duplicate_lead_email_rejected(db: AsyncSession, sales_user: User):
    service = LeadService(db)
    await service.create_lead(
        first_name="First", last_name="Lead", email="dupe@test.com",
        owner_id=sales_user.id,
    )
    await db.commit()

    from app.core.exceptions import BadRequestException
    with pytest.raises(BadRequestException, match="zaten var"):
        await service.create_lead(
            first_name="Second", last_name="Lead", email="dupe@test.com",
            owner_id=sales_user.id,
        )


@pytest.mark.asyncio
async def test_auto_create_lead_from_email(db: AsyncSession, sales_user: User):
    service = LeadService(db)
    lead = await service.auto_create_lead_from_email(
        from_address="john.doe@company.com",
        subject="Spare part inquiry",
        owner_id=sales_user.id,
    )
    await db.commit()

    assert lead is not None
    assert lead.first_name == "John"
    assert lead.last_name == "Doe"
    assert lead.source == "email"


@pytest.mark.asyncio
async def test_auto_create_lead_skips_existing_customer(db: AsyncSession, sales_user: User):
    # Create a customer first
    db.add(Customer(name="Existing", email="existing@corp.com", created_by=sales_user.id))
    await db.commit()

    service = LeadService(db)
    lead = await service.auto_create_lead_from_email(
        from_address="existing@corp.com",
        owner_id=sales_user.id,
    )
    assert lead is None  # Should not create lead
