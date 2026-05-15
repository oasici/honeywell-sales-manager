"""Tests for lead assignment rules — matching, round_robin, least_loaded."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.lead import Lead
from app.models.lead_assignment_rule import LeadAssignmentRule
from app.models.user import User
from app.services.lead_service import LeadService
from tests.factories import make_lead


async def _create_user(db: AsyncSession, email: str, name: str) -> User:
    """Helper to create a test user."""
    from tests.factories import DEFAULT_TENANT_ID

    user = User(
        # Round-15 Sprint 15k/l unblocker — match the canonical
        # single-tenant test id so factory-created leads inherit it.
        tenant_id=DEFAULT_TENANT_ID,
        email=email,
        full_name=name,
        hashed_password=hash_password("test123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def users(db: AsyncSession) -> list[User]:
    """Create multiple test users for assignment testing."""
    user_a = await _create_user(db, "rep_a@test.com", "Rep A")
    user_b = await _create_user(db, "rep_b@test.com", "Rep B")
    user_c = await _create_user(db, "rep_c@test.com", "Rep C")
    return [user_a, user_b, user_c]


@pytest.mark.asyncio
async def test_specific_user_assignment(db: AsyncSession, users: list[User]):
    """Lead matching a specific_user rule should be assigned to that user."""
    target_user = users[0]

    rule = LeadAssignmentRule(
        name="Sanayi Firmalari",
        criteria_json=json.dumps([{"field": "company", "op": "contains", "value": "sanayi"}]),
        assign_to_user_id=target_user.id,
        assign_mode="specific_user",
        priority=10,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    # Create a lead owned by a different user initially
    service = LeadService(db)
    lead = await service.create_lead(
        first_name="Ali",
        last_name="Yilmaz",
        email="ali@sanayifirma.com",
        company="ABC Sanayi Ltd",
        owner_id=users[1].id,
    )

    assert lead.owner_id == target_user.id


@pytest.mark.asyncio
async def test_rule_not_matching(db: AsyncSession, users: list[User]):
    """Lead not matching any rule criteria should keep its original owner."""
    rule = LeadAssignmentRule(
        name="Sanayi Firmalari",
        criteria_json=json.dumps([{"field": "company", "op": "contains", "value": "sanayi"}]),
        assign_to_user_id=users[0].id,
        assign_mode="specific_user",
        priority=10,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    service = LeadService(db)
    lead = await service.create_lead(
        first_name="Mehmet",
        last_name="Demir",
        email="mehmet@techfirma.com",
        company="Tech Solutions AS",
        owner_id=users[1].id,
    )

    # Should keep original owner since "sanayi" not in company
    assert lead.owner_id == users[1].id


@pytest.mark.asyncio
async def test_round_robin_assignment(db: AsyncSession, users: list[User]):
    """Round robin rule should distribute leads among active users."""
    rule = LeadAssignmentRule(
        name="Round Robin Tum Leadler",
        criteria_json=json.dumps([{"field": "source", "op": "eq", "value": "web"}]),
        assign_to_user_id=None,
        assign_mode="round_robin",
        priority=5,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    service = LeadService(db)
    assigned_owners = []

    for i in range(3):
        lead = await service.create_lead(
            first_name=f"Lead{i}",
            last_name="Test",
            email=f"lead{i}@web.com",
            source="web",
            owner_id=users[0].id,
        )
        assigned_owners.append(lead.owner_id)

    # Round robin should assign to different users (at least 2 distinct)
    assert len(set(assigned_owners)) >= 2


@pytest.mark.asyncio
async def test_least_loaded_assignment(db: AsyncSession, users: list[User]):
    """Least loaded rule should assign to user with fewest active leads."""
    # Pre-load user_a with leads via tenant-aware factory.
    for i in range(3):
        await make_lead(
            db,
            first_name=f"Existing{i}",
            last_name="Lead",
            email=f"existing{i}@test.com",
            source="manual",
            owner_id=users[0].id,
        )
    await db.flush()

    rule = LeadAssignmentRule(
        name="Least Loaded",
        criteria_json=json.dumps([{"field": "source", "op": "eq", "value": "import"}]),
        assign_to_user_id=None,
        assign_mode="least_loaded",
        priority=5,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    service = LeadService(db)
    lead = await service.create_lead(
        first_name="New",
        last_name="Import",
        email="new_import@test.com",
        source="import",
        owner_id=users[0].id,  # default, should be overridden
    )

    # Should NOT be assigned to users[0] who already has 3 leads
    # Should go to users[1] or users[2] who have 0 leads
    assert lead.owner_id in (users[1].id, users[2].id)


@pytest.mark.asyncio
async def test_inactive_rule_ignored(db: AsyncSession, users: list[User]):
    """Inactive rules should not be evaluated."""
    rule = LeadAssignmentRule(
        name="Inactive Rule",
        criteria_json=json.dumps([{"field": "company", "op": "contains", "value": "test"}]),
        assign_to_user_id=users[0].id,
        assign_mode="specific_user",
        priority=10,
        is_active=False,
    )
    db.add(rule)
    await db.flush()

    service = LeadService(db)
    lead = await service.create_lead(
        first_name="Test",
        last_name="User",
        email="testuser@testcompany.com",
        company="Test Company",
        owner_id=users[1].id,
    )

    # Should keep original owner since rule is inactive
    assert lead.owner_id == users[1].id


@pytest.mark.asyncio
async def test_priority_ordering(db: AsyncSession, users: list[User]):
    """Higher priority rules should be evaluated first and win."""
    # Low priority: assign to user B
    low_rule = LeadAssignmentRule(
        name="Low Priority",
        criteria_json=json.dumps([{"field": "company", "op": "contains", "value": "firma"}]),
        assign_to_user_id=users[1].id,
        assign_mode="specific_user",
        priority=1,
        is_active=True,
    )
    db.add(low_rule)

    # High priority: assign to user C
    high_rule = LeadAssignmentRule(
        name="High Priority",
        criteria_json=json.dumps([{"field": "company", "op": "contains", "value": "firma"}]),
        assign_to_user_id=users[2].id,
        assign_mode="specific_user",
        priority=10,
        is_active=True,
    )
    db.add(high_rule)
    await db.flush()

    service = LeadService(db)
    lead = await service.create_lead(
        first_name="Priority",
        last_name="Test",
        email="priority@firma.com",
        company="Buyuk Firma AS",
        owner_id=users[0].id,
    )

    # High priority rule should win
    assert lead.owner_id == users[2].id
