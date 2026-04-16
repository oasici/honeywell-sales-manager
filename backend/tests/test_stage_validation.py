"""Tests for stage validation service — guided selling requirements."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.stage_requirement import StageRequirement
from app.models.user import User
from app.services.stage_validation_service import validate_stage_transition


@pytest_asyncio.fixture
async def sales_user(db: AsyncSession) -> User:
    user = User(
        email="rep_stage@test.com",
        full_name="Stage Test Rep",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def opportunity_no_amount(db: AsyncSession, sales_user: User) -> Opportunity:
    """Opportunity missing amount and customer_id."""
    opp = Opportunity(
        title="Test Opp Missing Fields",
        stage="prospecting",
        owner_id=sales_user.id,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest_asyncio.fixture
async def opportunity_complete(db: AsyncSession, sales_user: User) -> Opportunity:
    """Opportunity with all fields filled."""
    opp = Opportunity(
        title="Test Opp Complete",
        stage="prospecting",
        amount=50000.0,
        owner_id=sales_user.id,
        customer_id=None,  # will be set below
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest_asyncio.fixture
async def stage_requirement_qualified(db: AsyncSession) -> StageRequirement:
    """Stage requirement for qualified: needs amount."""
    req = StageRequirement(
        stage="qualified",
        required_fields_json='["amount"]',
        validation_rules_json=None,
        coaching_tips_json='["Karar vericiyi tanimlayin","Butceyi dogrulayin"]',
        is_active=True,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


@pytest_asyncio.fixture
async def stage_requirement_proposal(db: AsyncSession) -> StageRequirement:
    """Stage requirement for proposal: needs amount and has_quote."""
    req = StageRequirement(
        stage="proposal",
        required_fields_json='["amount","customer_id"]',
        validation_rules_json='[{"rule":"has_quote","message":"En az 1 teklif gerekli"}]',
        coaching_tips_json='["Teklif detaylarini kontrol edin"]',
        is_active=True,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


# -- Validation blocks transition when required field missing --

@pytest.mark.asyncio
async def test_validation_blocks_when_required_field_missing(
    db: AsyncSession,
    opportunity_no_amount: Opportunity,
    stage_requirement_qualified: StageRequirement,
):
    """Validation fails when opportunity is missing amount for qualified stage."""
    result = await validate_stage_transition(db, opportunity_no_amount, "qualified")

    assert result["valid"] is False
    assert len(result["errors"]) >= 1
    assert any("amount" in e for e in result["errors"])


# -- Validation passes when requirements met --

@pytest.mark.asyncio
async def test_validation_passes_when_requirements_met(
    db: AsyncSession,
    opportunity_complete: Opportunity,
    stage_requirement_qualified: StageRequirement,
):
    """Validation passes when opportunity has amount for qualified stage."""
    result = await validate_stage_transition(db, opportunity_complete, "qualified")

    assert result["valid"] is True
    assert len(result["errors"]) == 0


# -- Coaching tips returned --

@pytest.mark.asyncio
async def test_coaching_tips_returned(
    db: AsyncSession,
    opportunity_complete: Opportunity,
    stage_requirement_qualified: StageRequirement,
):
    """Coaching tips are returned for the target stage."""
    result = await validate_stage_transition(db, opportunity_complete, "qualified")

    assert len(result["tips"]) == 2
    assert "Karar vericiyi tanimlayin" in result["tips"]
    assert "Butceyi dogrulayin" in result["tips"]


# -- No requirement defined = auto-pass --

@pytest.mark.asyncio
async def test_no_requirement_auto_passes(
    db: AsyncSession,
    opportunity_no_amount: Opportunity,
):
    """If no StageRequirement exists for stage, validation passes."""
    result = await validate_stage_transition(db, opportunity_no_amount, "negotiation")

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["tips"] == []


# -- has_quote rule validation --

@pytest.mark.asyncio
async def test_has_quote_rule_fails_without_quote(
    db: AsyncSession,
    opportunity_complete: Opportunity,
    stage_requirement_proposal: StageRequirement,
):
    """has_quote validation rule fails when no quote exists for opportunity."""
    result = await validate_stage_transition(db, opportunity_complete, "proposal")

    # Should fail on both customer_id (None) and has_quote
    assert result["valid"] is False
    assert any("teklif" in e.lower() for e in result["errors"])


@pytest.mark.asyncio
async def test_has_quote_rule_passes_with_quote(
    db: AsyncSession,
    sales_user: User,
    stage_requirement_proposal: StageRequirement,
):
    """has_quote validation rule passes when a quote exists for opportunity."""
    from app.models.customer import Customer

    # Create customer
    customer = Customer(name="Test Customer", email="c@test.com")
    db.add(customer)
    await db.flush()

    # Create opportunity with all required fields
    opp = Opportunity(
        title="Opp With Quote",
        stage="qualified",
        amount=100000.0,
        owner_id=sales_user.id,
        customer_id=customer.id,
    )
    db.add(opp)
    await db.flush()
    await db.refresh(opp)

    # Create a quote for this opportunity
    quote = Quote(
        quote_number="HW-TEST-001",
        opportunity_id=opp.id,
        customer_id=customer.id,
        created_by=sales_user.id,
    )
    db.add(quote)
    await db.commit()

    result = await validate_stage_transition(db, opp, "proposal")

    assert result["valid"] is True
    assert len(result["errors"]) == 0
