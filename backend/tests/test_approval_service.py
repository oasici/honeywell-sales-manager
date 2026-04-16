"""Tests for multi-level approval routing -- rule evaluation, chain creation, decisions."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.user import User
from app.services.approval_service import ApprovalService


@pytest_asyncio.fixture
async def manager_user(db: AsyncSession) -> User:
    user = User(
        email="manager@test.com",
        full_name="Sales Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def approver_user(db: AsyncSession) -> User:
    user = User(
        email="approver@test.com",
        full_name="Approver User",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


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
def _enable_approval_routing():
    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.FEATURE_APPROVAL_ROUTING = True
        yield


# -- Rule Evaluation Tests --

@pytest.mark.asyncio
async def test_evaluate_rules_matches_gt(
    db: AsyncSession, approver_user: User,
):
    """Rule with gt operator matches when entity value exceeds threshold."""
    rule = ApprovalRule(
        name="High discount approval",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=15.0,
        threshold_operator="gt",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    matched = await service.evaluate_rules("quote", {"discount_pct": 20.0})

    assert len(matched) == 1
    assert matched[0].name == "High discount approval"


@pytest.mark.asyncio
async def test_evaluate_rules_no_match_below_threshold(
    db: AsyncSession, approver_user: User,
):
    """Rule does not match when entity value is below threshold."""
    rule = ApprovalRule(
        name="High discount approval",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=15.0,
        threshold_operator="gt",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    matched = await service.evaluate_rules("quote", {"discount_pct": 10.0})

    assert len(matched) == 0


@pytest.mark.asyncio
async def test_evaluate_rules_gte_operator(
    db: AsyncSession, approver_user: User,
):
    """Rule with gte operator matches when entity value equals threshold."""
    rule = ApprovalRule(
        name="Deal amount gate",
        entity_type="quote",
        condition_type="deal_amount",
        threshold_value=100000.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=5,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    matched = await service.evaluate_rules("quote", {"deal_amount": 100000.0})

    assert len(matched) == 1


@pytest.mark.asyncio
async def test_evaluate_rules_skips_inactive(
    db: AsyncSession, approver_user: User,
):
    """Inactive rules are not evaluated."""
    rule = ApprovalRule(
        name="Disabled rule",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=5.0,
        threshold_operator="gt",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=False,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    matched = await service.evaluate_rules("quote", {"discount_pct": 50.0})

    assert len(matched) == 0


@pytest.mark.asyncio
async def test_evaluate_rules_sorted_by_priority(
    db: AsyncSession, approver_user: User,
):
    """Matched rules are returned sorted by priority descending."""
    low_priority = ApprovalRule(
        name="Low priority",
        entity_type="quote",
        condition_type="grand_total",
        threshold_value=1000.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=1,
        is_active=True,
    )
    high_priority = ApprovalRule(
        name="High priority",
        entity_type="quote",
        condition_type="grand_total",
        threshold_value=1000.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=100,
        is_active=True,
    )
    db.add_all([low_priority, high_priority])
    await db.commit()

    service = ApprovalService(db)
    matched = await service.evaluate_rules("quote", {"grand_total": 5000.0})

    assert len(matched) == 2
    assert matched[0].name == "High priority"
    assert matched[1].name == "Low priority"


# -- Chain Creation Tests --

@pytest.mark.asyncio
async def test_submit_for_approval_creates_chain(
    db: AsyncSession, sales_user: User, approver_user: User,
):
    """Submit creates one ApprovalRequest per matching rule."""
    rule_1 = ApprovalRule(
        name="Discount check",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=10.0,
        threshold_operator="gt",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=True,
    )
    rule_2 = ApprovalRule(
        name="Amount check",
        entity_type="quote",
        condition_type="grand_total",
        threshold_value=50000.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=5,
        is_active=True,
    )
    db.add_all([rule_1, rule_2])
    await db.commit()

    service = ApprovalService(db)
    requests = await service.submit_for_approval(
        entity_type="quote",
        entity_id=42,
        requested_by=sales_user.id,
        entity_data={"discount_pct": 25.0, "grand_total": 75000.0},
    )
    await db.commit()

    assert len(requests) == 2
    assert requests[0].level == 1
    assert requests[1].level == 2
    assert all(r.status == "pending" for r in requests)
    assert all(r.assigned_to == approver_user.id for r in requests)


@pytest.mark.asyncio
async def test_no_rules_returns_empty_list(
    db: AsyncSession, sales_user: User,
):
    """No matching rules = auto-approve (empty list returned)."""
    service = ApprovalService(db)
    requests = await service.submit_for_approval(
        entity_type="quote",
        entity_id=99,
        requested_by=sales_user.id,
        entity_data={"discount_pct": 5.0},
    )

    assert requests == []


# -- Multi-Level Approval Flow --

@pytest.mark.asyncio
async def test_multi_level_approval_flow(
    db: AsyncSession, sales_user: User, approver_user: User,
):
    """Approve all levels to achieve fully-approved state."""
    rule = ApprovalRule(
        name="High value",
        entity_type="quote",
        condition_type="grand_total",
        threshold_value=10000.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    requests = await service.submit_for_approval(
        entity_type="quote",
        entity_id=1,
        requested_by=sales_user.id,
        entity_data={"grand_total": 50000.0},
    )
    await db.commit()

    assert len(requests) == 1
    assert not await service.is_fully_approved("quote", 1)

    # Approve
    await service.approve(requests[0].id, approver_user.id, "Looks good")
    await db.commit()

    assert await service.is_fully_approved("quote", 1)


# -- Rejection Cascade --

@pytest.mark.asyncio
async def test_rejection_cascades_to_all_pending(
    db: AsyncSession, sales_user: User, approver_user: User,
):
    """Rejecting one request also rejects all other pending requests for the same entity."""
    rule_1 = ApprovalRule(
        name="Rule A",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=5.0,
        threshold_operator="gt",
        approver_user_id=approver_user.id,
        priority=10,
        is_active=True,
    )
    rule_2 = ApprovalRule(
        name="Rule B",
        entity_type="quote",
        condition_type="grand_total",
        threshold_value=1000.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=5,
        is_active=True,
    )
    db.add_all([rule_1, rule_2])
    await db.commit()

    service = ApprovalService(db)
    requests = await service.submit_for_approval(
        entity_type="quote",
        entity_id=10,
        requested_by=sales_user.id,
        entity_data={"discount_pct": 20.0, "grand_total": 5000.0},
    )
    await db.commit()

    assert len(requests) == 2

    # Reject the first request
    await service.reject(requests[0].id, approver_user.id, "Too risky")
    await db.commit()

    # Both should be rejected
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.entity_type == "quote",
            ApprovalRequest.entity_id == 10,
        )
    )
    all_requests = result.scalars().all()
    assert all(r.status == "rejected" for r in all_requests)
    assert not await service.is_fully_approved("quote", 10)


# -- Edge Cases --

@pytest.mark.asyncio
async def test_approve_already_decided_raises(
    db: AsyncSession, sales_user: User, approver_user: User,
):
    """Cannot approve a request that is already decided."""
    rule = ApprovalRule(
        name="Simple rule",
        entity_type="quote",
        condition_type="grand_total",
        threshold_value=100.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=1,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    requests = await service.submit_for_approval(
        entity_type="quote",
        entity_id=50,
        requested_by=sales_user.id,
        entity_data={"grand_total": 500.0},
    )
    await db.commit()

    await service.approve(requests[0].id, approver_user.id)
    await db.commit()

    from app.core.exceptions import BadRequestException
    with pytest.raises(BadRequestException, match="zaten islendi"):
        await service.approve(requests[0].id, approver_user.id)


@pytest.mark.asyncio
async def test_reject_nonexistent_raises(db: AsyncSession):
    """Rejecting a nonexistent request raises NotFoundException."""
    service = ApprovalService(db)

    from app.core.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await service.reject(99999, 1)


@pytest.mark.asyncio
async def test_get_pending_approvals(
    db: AsyncSession, sales_user: User, approver_user: User,
):
    """Pending approvals are returned for the assigned user."""
    rule = ApprovalRule(
        name="Pending test rule",
        entity_type="quote",
        condition_type="discount_pct",
        threshold_value=1.0,
        threshold_operator="gte",
        approver_user_id=approver_user.id,
        priority=1,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    service = ApprovalService(db)
    await service.submit_for_approval(
        entity_type="quote",
        entity_id=77,
        requested_by=sales_user.id,
        entity_data={"discount_pct": 5.0},
    )
    await db.commit()

    pending = await service.get_pending_approvals(approver_user.id)
    assert len(pending) >= 1
    assert all(r.status == "pending" for r in pending)
    assert all(r.assigned_to == approver_user.id for r in pending)

    # Sales user should have no pending approvals
    sales_pending = await service.get_pending_approvals(sales_user.id)
    assert len(sales_pending) == 0


@pytest.mark.asyncio
async def test_is_fully_approved_no_requests(db: AsyncSession):
    """Entity with no approval requests is considered auto-approved."""
    service = ApprovalService(db)
    assert await service.is_fully_approved("quote", 12345) is True
