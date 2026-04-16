"""Edge case tests for the approval service."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.security import hash_password
from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.user import User
from app.services.approval_service import ApprovalService


@pytest_asyncio.fixture
async def sales_rep(db: AsyncSession) -> User:
    """A sales_rep user (non-manager)."""
    user = User(
        email="rep@test.com",
        full_name="Sales Rep",
        hashed_password=hash_password("pass123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def approver_user(db: AsyncSession) -> User:
    """A user designated as the approver."""
    user = User(
        email="approver@test.com",
        full_name="Approver",
        hashed_password=hash_password("pass123"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def delegate_user(db: AsyncSession) -> User:
    """A delegate user for delegation tests."""
    user = User(
        email="delegate@test.com",
        full_name="Delegate User",
        hashed_password=hash_password("pass123"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def discount_rule(
    db: AsyncSession, approver_user: User,
) -> ApprovalRule:
    """An approval rule that triggers when discount_pct > 10."""
    rule = ApprovalRule(
        name="High discount rule",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=10.0,
        threshold_operator="gt",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=True,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


class TestDuplicateSubmissionIdempotency:
    """Submitting the same entity twice should return the existing chain."""

    @pytest.mark.asyncio
    async def test_duplicate_submission_returns_existing_chain(
        self, db: AsyncSession, sales_rep: User, discount_rule: ApprovalRule,
    ):
        service = ApprovalService(db)
        entity_data = {"discount_pct": 15.0}

        first_chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=999,
            requested_by=sales_rep.id,
            entity_data=entity_data,
        )
        await db.commit()

        second_chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=999,
            requested_by=sales_rep.id,
            entity_data=entity_data,
        )

        assert len(first_chain) == len(second_chain)
        first_ids = {r.id for r in first_chain}
        second_ids = {r.id for r in second_chain}
        assert first_ids == second_ids, "Second submission should return the same requests"


class TestSelfApprovalPrevention:
    """Non-manager users cannot approve their own requests."""

    @pytest.mark.asyncio
    async def test_self_approval_blocked_for_sales_rep(
        self, db: AsyncSession, sales_rep: User, discount_rule: ApprovalRule,
    ):
        service = ApprovalService(db)
        entity_data = {"discount_pct": 15.0}

        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=1001,
            requested_by=sales_rep.id,
            entity_data=entity_data,
        )
        await db.commit()

        assert len(chain) > 0
        request_id = chain[0].id

        with pytest.raises(BadRequestException, match="onaylayamazsiniz"):
            await service.approve(request_id, user_id=sales_rep.id)

    @pytest.mark.asyncio
    async def test_self_approval_allowed_for_manager(
        self, db: AsyncSession, approver_user: User,
    ):
        """A sales_manager who requested can also approve (bypass self-check)."""
        rule = ApprovalRule(
            name="Manager self-approve rule",
            entity_type="quote",
            condition_type="grand_total",
            threshold_value=1000.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            priority=5,
            is_active=True,
        )
        db.add(rule)
        await db.commit()

        service = ApprovalService(db)
        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=1002,
            requested_by=approver_user.id,
            entity_data={"grand_total": 5000.0},
        )
        await db.commit()

        assert len(chain) > 0
        approved = await service.approve(chain[0].id, user_id=approver_user.id)
        assert approved.status == "approved"


class TestDelegation:
    """Delegation routes approval to the delegate user."""

    @pytest.mark.asyncio
    async def test_active_delegation_assigns_to_delegate(
        self,
        db: AsyncSession,
        sales_rep: User,
        approver_user: User,
        delegate_user: User,
    ):
        rule = ApprovalRule(
            name="Delegated rule",
            entity_type="quote",
            condition_type="discount_pct",
            threshold_value=5.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            delegate_to=delegate_user.id,
            delegate_until=datetime.now(timezone.utc) + timedelta(days=7),
            priority=10,
            is_active=True,
        )
        db.add(rule)
        await db.commit()

        service = ApprovalService(db)
        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=2001,
            requested_by=sales_rep.id,
            entity_data={"discount_pct": 10.0},
        )

        assert len(chain) > 0
        assert chain[0].assigned_to == delegate_user.id
        assert chain[0].comments is not None
        assert "Yetki devri" in chain[0].comments

    @pytest.mark.asyncio
    async def test_expired_delegation_assigns_to_original_approver(
        self,
        db: AsyncSession,
        sales_rep: User,
        approver_user: User,
        delegate_user: User,
    ):
        rule = ApprovalRule(
            name="Expired delegation rule",
            entity_type="quote",
            condition_type="discount_pct",
            threshold_value=5.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            delegate_to=delegate_user.id,
            delegate_until=datetime.now(timezone.utc) - timedelta(days=1),
            priority=10,
            is_active=True,
        )
        db.add(rule)
        await db.commit()

        service = ApprovalService(db)
        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=2002,
            requested_by=sales_rep.id,
            entity_data={"discount_pct": 10.0},
        )

        assert len(chain) > 0
        assert chain[0].assigned_to == approver_user.id
        assert chain[0].comments is None


class TestParallelChainMode:
    """Parallel chain mode sets all requests to level 1."""

    @pytest.mark.asyncio
    async def test_parallel_chain_creates_all_at_level_one(
        self, db: AsyncSession, sales_rep: User, approver_user: User,
    ):
        rule_a = ApprovalRule(
            name="Parallel rule A",
            entity_type="quote",
            condition_type="discount_pct",
            threshold_value=5.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            chain_mode="parallel",
            priority=20,
            is_active=True,
        )
        rule_b = ApprovalRule(
            name="Parallel rule B",
            entity_type="quote",
            condition_type="grand_total",
            threshold_value=100.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            chain_mode="parallel",
            priority=10,
            is_active=True,
        )
        db.add_all([rule_a, rule_b])
        await db.commit()

        service = ApprovalService(db)
        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=3001,
            requested_by=sales_rep.id,
            entity_data={"discount_pct": 15.0, "grand_total": 500.0},
        )

        assert len(chain) == 2
        assert all(r.level == 1 for r in chain), (
            "Parallel mode should set all requests to level 1"
        )


class TestRejectCascade:
    """Rejecting one request cascades to all pending requests for the same entity."""

    @pytest.mark.asyncio
    async def test_reject_cascades_all_pending_requests(
        self, db: AsyncSession, sales_rep: User, approver_user: User,
    ):
        rule_1 = ApprovalRule(
            name="Cascade rule 1",
            entity_type="quote",
            condition_type="discount_pct",
            threshold_value=5.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            priority=20,
            is_active=True,
        )
        rule_2 = ApprovalRule(
            name="Cascade rule 2",
            entity_type="quote",
            condition_type="grand_total",
            threshold_value=100.0,
            threshold_operator="gt",
            approver_user_id=approver_user.id,
            priority=10,
            is_active=True,
        )
        db.add_all([rule_1, rule_2])
        await db.commit()

        service = ApprovalService(db)
        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=4001,
            requested_by=sales_rep.id,
            entity_data={"discount_pct": 15.0, "grand_total": 500.0},
        )
        await db.commit()

        assert len(chain) == 2

        # Reject the first request
        await service.reject(chain[0].id, user_id=approver_user.id, comments="Too high")
        await db.commit()

        # Reload all requests for this entity
        result = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.entity_type == "quote",
                ApprovalRequest.entity_id == 4001,
            )
        )
        all_requests = result.scalars().all()

        assert all(r.status == "rejected" for r in all_requests), (
            "All pending requests should be rejected after cascade"
        )

    @pytest.mark.asyncio
    async def test_entity_not_fully_approved_after_rejection(
        self, db: AsyncSession, sales_rep: User, approver_user: User,
        discount_rule: ApprovalRule,
    ):
        service = ApprovalService(db)
        chain = await service.submit_for_approval(
            entity_type="quote",
            entity_id=4002,
            requested_by=sales_rep.id,
            entity_data={"discount_pct": 15.0},
        )
        await db.commit()

        await service.reject(chain[0].id, user_id=approver_user.id)
        await db.commit()

        is_approved = await service.is_fully_approved("quote", 4002)
        assert is_approved is False
