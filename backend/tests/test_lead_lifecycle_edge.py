"""Edge case tests for lead lifecycle service."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.security import hash_password
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.lead import Lead
from app.models.user import User
from tests.factories import DEFAULT_TENANT_ID, make_customer
from app.services.lead_service import (
    INACTIVITY_PENALTY_POINTS,
    INACTIVITY_THRESHOLD_DAYS,
    LeadService,
)


@pytest_asyncio.fixture
async def lead_owner(db: AsyncSession) -> User:
    # Round-15 Sprint 15k/l unblocker — tenant_id threaded so derived
    # rows (leads, customers) inherit the canonical single-tenant id.
    user = User(
        tenant_id=DEFAULT_TENANT_ID,
        email="lead_owner@test.com",
        full_name="Lead Owner",
        hashed_password=hash_password("pass123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def manager_user(db: AsyncSession) -> User:
    user = User(
        tenant_id=DEFAULT_TENANT_ID,
        email="manager_lead@test.com",
        full_name="Manager Lead",
        hashed_password=hash_password("pass123"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestScoreExplanationAccuracy:
    """Score breakdown should include expected factors for known lead data."""

    @pytest.mark.asyncio
    async def test_breakdown_includes_email_and_company_factors(
        self, db: AsyncSession, lead_owner: User,
    ):
        service = LeadService(db)
        lead = await service.create_lead(
            first_name="Score",
            last_name="Test",
            email="score.test@external.com",
            phone="+905551234567",
            company="TestCorp",
            title="Manager",
            source="manual",
            owner_id=lead_owner.id,
        )
        await db.commit()

        breakdown = await service.compute_score_breakdown(lead)
        factor_names = [item["factor"] for item in breakdown]

        assert "email" in factor_names, "Email factor should be present"
        assert "phone" in factor_names, "Phone factor should be present"
        assert "company" in factor_names, "Company factor should be present"
        assert "title" in factor_names, "Title factor should be present"

    @pytest.mark.asyncio
    async def test_score_greater_than_zero_with_complete_data(
        self, db: AsyncSession, lead_owner: User,
    ):
        service = LeadService(db)
        lead = await service.create_lead(
            first_name="Complete",
            last_name="Lead",
            email="complete.lead@external.com",
            phone="+905559876543",
            company="BigCorp",
            title="Director",
            source="referral",
            owner_id=lead_owner.id,
        )
        await db.commit()

        assert lead.lead_score > 0, "Lead with complete data should have a positive score"


class TestTemporalDecay:
    """Leads with old email interactions should receive an inactivity penalty."""

    @pytest.mark.asyncio
    async def test_inactivity_penalty_applied_for_old_email(
        self, db: AsyncSession, lead_owner: User,
    ):
        service = LeadService(db)
        lead = await service.create_lead(
            first_name="Inactive",
            last_name="Lead",
            email="inactive.lead@external.com",
            source="email",
            owner_id=lead_owner.id,
        )
        await db.commit()

        # Create an old email interaction beyond the inactivity threshold
        old_date = datetime.now(timezone.utc) - timedelta(days=45)
        old_email = EmailRequest(
            message_id="msg-old-001",
            from_address="inactive.lead@external.com",
            subject="Old inquiry",
            received_at=old_date,
            status="parsed",
        )
        db.add(old_email)
        await db.commit()

        # Re-score to pick up the inactivity penalty
        lead.lead_score, _ = await service._compute_score(lead)
        breakdown_items = (await service._compute_score(lead))[1]

        decay_factors = [
            item for item in breakdown_items if item["factor"] == "inactivity_decay"
        ]
        assert len(decay_factors) == 1, "Should have exactly one inactivity decay factor"
        assert decay_factors[0]["points"] < 0, "Inactivity decay should be negative"


class TestConvertAlreadyConvertedLead:
    """Converting an already-converted lead should raise BadRequestException."""

    @pytest.mark.asyncio
    async def test_convert_already_converted_raises_error(
        self, db: AsyncSession, lead_owner: User, manager_user: User,
    ):
        service = LeadService(db)
        lead = await service.create_lead(
            first_name="Convert",
            last_name="Twice",
            email="convert.twice@external.com",
            source="manual",
            owner_id=lead_owner.id,
        )
        await db.commit()

        # Qualify and convert
        lead = await service.update_lead(lead.id, status="qualified")
        await db.commit()

        await service.convert_lead(
            lead_id=lead.id,
            user_id=manager_user.id,
            create_opportunity=False,
        )
        await db.commit()

        # Second conversion attempt should fail
        with pytest.raises(BadRequestException, match="zaten donusturulmus"):
            await service.convert_lead(
                lead_id=lead.id,
                user_id=manager_user.id,
            )


class TestConvertNonQualifiedLead:
    """Converting a lead that is not qualified or contacted should raise."""

    @pytest.mark.asyncio
    async def test_convert_new_lead_raises_error(
        self, db: AsyncSession, lead_owner: User, manager_user: User,
    ):
        service = LeadService(db)
        lead = await service.create_lead(
            first_name="New",
            last_name="Lead",
            email="new.lead@external.com",
            source="manual",
            owner_id=lead_owner.id,
        )
        await db.commit()

        assert lead.status == "new"

        with pytest.raises(BadRequestException, match="donusturulebilir"):
            await service.convert_lead(
                lead_id=lead.id,
                user_id=manager_user.id,
            )

    @pytest.mark.asyncio
    async def test_convert_unqualified_lead_raises_error(
        self, db: AsyncSession, lead_owner: User, manager_user: User,
    ):
        service = LeadService(db)
        lead = await service.create_lead(
            first_name="Unqualified",
            last_name="Lead",
            email="unqualified.lead@external.com",
            source="manual",
            owner_id=lead_owner.id,
        )
        lead = await service.update_lead(lead.id, status="unqualified")
        await db.commit()

        with pytest.raises(BadRequestException, match="donusturulebilir"):
            await service.convert_lead(
                lead_id=lead.id,
                user_id=manager_user.id,
            )


class TestDuplicateEmailAcrossLeadAndCustomer:
    """auto_create_lead_from_email should skip if a customer with the email exists."""

    @pytest.mark.asyncio
    async def test_skips_lead_creation_if_customer_exists(
        self, db: AsyncSession, lead_owner: User,
    ):
        customer = await make_customer(
            db,
            name="Existing Customer",
            email="existing@customer.com",
            company="ExistCo",
            phone="555-0000",
            created_by=lead_owner.id,
        )
        await db.commit()

        service = LeadService(db)
        result = await service.auto_create_lead_from_email(
            from_address="existing@customer.com",
            subject="Hello",
            owner_id=lead_owner.id,
        )

        assert result is None, "Should not create a lead when customer already exists"

    @pytest.mark.asyncio
    async def test_skips_lead_creation_if_lead_exists(
        self, db: AsyncSession, lead_owner: User,
    ):
        service = LeadService(db)
        await service.create_lead(
            first_name="Existing",
            last_name="Lead",
            email="existing@lead.com",
            source="manual",
            owner_id=lead_owner.id,
        )
        await db.commit()

        result = await service.auto_create_lead_from_email(
            from_address="existing@lead.com",
            subject="Follow up",
            owner_id=lead_owner.id,
        )

        assert result is None, "Should not create a duplicate lead"


class TestBatchRescore:
    """rescore_all_leads should return the count of re-scored leads."""

    @pytest.mark.asyncio
    async def test_rescore_returns_correct_count(
        self, db: AsyncSession, lead_owner: User,
    ):
        service = LeadService(db)

        for i in range(3):
            await service.create_lead(
                first_name=f"Batch{i}",
                last_name="Lead",
                email=f"batch{i}@external.com",
                source="manual",
                owner_id=lead_owner.id,
            )
        await db.commit()

        count = await service.rescore_all_leads()
        assert count == 3, f"Expected 3 leads re-scored, got {count}"
