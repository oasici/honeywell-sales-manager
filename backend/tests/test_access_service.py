"""Tests for AccessService: ownership, team access, sharing rules, manager override."""
from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.team import AccountTeam, SharingRule
from app.models.user import User
from app.services.access_service import AccessService


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _create_user(db: AsyncSession, email: str, role: str = "sales_rep") -> User:
    user = User(
        tenant_id=_TENANT_ID,
        email=email,
        full_name=f"Test {role}",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_customer(db: AsyncSession, owner_id: int) -> Customer:
    customer = Customer(
        tenant_id=_TENANT_ID,
        name="Test Musteri",
        email=f"customer_{owner_id}@example.com",
        company="Test Sanayi A.S.",
        created_by=owner_id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def _create_opportunity(
    db: AsyncSession, owner_id: int, customer_id: int
) -> Opportunity:
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="Test Firsat",
        stage="prospecting",
        owner_id=owner_id,
        customer_id=customer_id,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


# ── Manager Override ──


@pytest.mark.asyncio
async def test_manager_has_full_access(db: AsyncSession):
    manager = await _create_user(db, "mgr_access@test.com", "sales_manager")
    rep = await _create_user(db, "rep_access@test.com", "sales_rep")
    customer = await _create_customer(db, rep.id)

    service = AccessService(db)
    result = await service.can_access(
        user_id=manager.id,
        user_role=manager.role,
        entity_type="customer",
        entity_id=customer.id,
    )
    assert result is True


@pytest.mark.asyncio
async def test_manager_gets_none_for_accessible_ids(db: AsyncSession):
    manager = await _create_user(db, "mgr_ids@test.com", "sales_manager")

    service = AccessService(db)
    result = await service.get_accessible_customer_ids(manager.id, manager.role)
    assert result is None


# ── Ownership Access ──


@pytest.mark.asyncio
async def test_owner_can_access_own_entity(db: AsyncSession):
    rep = await _create_user(db, "owner_test@test.com", "sales_rep")
    customer = await _create_customer(db, rep.id)

    service = AccessService(db)
    result = await service.can_access(
        user_id=rep.id,
        user_role=rep.role,
        entity_type="customer",
        entity_id=customer.id,
        owner_id=rep.id,
    )
    assert result is True


@pytest.mark.asyncio
async def test_non_owner_cannot_access_without_team_or_rule(db: AsyncSession):
    rep_a = await _create_user(db, "rep_a_acc@test.com", "sales_rep")
    rep_b = await _create_user(db, "rep_b_acc@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)

    service = AccessService(db)
    result = await service.can_access(
        user_id=rep_b.id,
        user_role=rep_b.role,
        entity_type="customer",
        entity_id=customer.id,
        owner_id=rep_a.id,
    )
    assert result is False


# ── Team Membership Access ──


@pytest.mark.asyncio
async def test_team_member_can_access_customer(db: AsyncSession):
    rep_a = await _create_user(db, "team_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "team_member@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)

    service = AccessService(db)
    await service.add_team_member(customer.id, rep_b.id, role="member")
    await db.commit()

    result = await service.can_access(
        user_id=rep_b.id,
        user_role=rep_b.role,
        entity_type="customer",
        entity_id=customer.id,
    )
    assert result is True


@pytest.mark.asyncio
async def test_team_member_can_access_linked_opportunity(db: AsyncSession):
    rep_a = await _create_user(db, "opp_team_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "opp_team_member@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)
    opp = await _create_opportunity(db, rep_a.id, customer.id)

    service = AccessService(db)
    await service.add_team_member(customer.id, rep_b.id, role="member")
    await db.commit()

    result = await service.can_access(
        user_id=rep_b.id,
        user_role=rep_b.role,
        entity_type="opportunity",
        entity_id=opp.id,
    )
    assert result is True


# ── Team CRUD ──


@pytest.mark.asyncio
async def test_add_and_get_team_members(db: AsyncSession):
    rep_a = await _create_user(db, "crud_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "crud_member@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)

    service = AccessService(db)
    member = await service.add_team_member(customer.id, rep_b.id, role="viewer")
    await db.commit()

    assert member.role == "viewer"
    assert member.user_id == rep_b.id

    members = await service.get_team_members(customer.id)
    assert len(members) == 1
    assert members[0].user_id == rep_b.id


@pytest.mark.asyncio
async def test_remove_team_member(db: AsyncSession):
    rep_a = await _create_user(db, "rm_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "rm_member@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)

    service = AccessService(db)
    await service.add_team_member(customer.id, rep_b.id)
    await db.commit()

    await service.remove_team_member(customer.id, rep_b.id)
    await db.commit()

    members = await service.get_team_members(customer.id)
    assert len(members) == 0


# ── Accessible Customer IDs ──


@pytest.mark.asyncio
async def test_get_accessible_customer_ids_includes_owned_and_team(db: AsyncSession):
    rep = await _create_user(db, "ids_rep@test.com", "sales_rep")
    other = await _create_user(db, "ids_other@test.com", "sales_rep")

    own_customer = await _create_customer(db, rep.id)
    team_customer = Customer(
        tenant_id=_TENANT_ID,
        name="Takim Musteri",
        email="team_cust@example.com",
        company="Takim Sanayi",
        created_by=other.id,
    )
    db.add(team_customer)
    await db.commit()
    await db.refresh(team_customer)

    service = AccessService(db)
    await service.add_team_member(team_customer.id, rep.id, role="member")
    await db.commit()

    ids = await service.get_accessible_customer_ids(rep.id, rep.role)
    assert ids is not None
    assert own_customer.id in ids
    assert team_customer.id in ids


# ── Sharing Rule Access ──


@pytest.mark.asyncio
async def test_sharing_rule_grants_access_by_role(db: AsyncSession):
    rep_a = await _create_user(db, "rule_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "rule_target@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)

    rule = SharingRule(
        name="Sanayi Sirketleri Paylasimi",
        entity_type="customer",
        criteria_json=json.dumps({
            "field": "company",
            "operator": "contains",
            "value": "Sanayi",
        }),
        share_with_role="sales_rep",
        access_level="read",
    )
    db.add(rule)
    await db.commit()

    service = AccessService(db)
    result = await service.can_access(
        user_id=rep_b.id,
        user_role=rep_b.role,
        entity_type="customer",
        entity_id=customer.id,
    )
    assert result is True


@pytest.mark.asyncio
async def test_sharing_rule_grants_access_by_user_id(db: AsyncSession):
    rep_a = await _create_user(db, "rule_u_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "rule_u_target@test.com", "sales_rep")
    customer = await _create_customer(db, rep_a.id)

    rule = SharingRule(
        name="Belirli Kullanici Paylasimi",
        entity_type="customer",
        criteria_json=json.dumps({
            "field": "company",
            "operator": "contains",
            "value": "Sanayi",
        }),
        share_with_user_id=rep_b.id,
        access_level="read",
    )
    db.add(rule)
    await db.commit()

    service = AccessService(db)
    result = await service.can_access(
        user_id=rep_b.id,
        user_role=rep_b.role,
        entity_type="customer",
        entity_id=customer.id,
    )
    assert result is True


@pytest.mark.asyncio
async def test_sharing_rule_no_match_denies_access(db: AsyncSession):
    rep_a = await _create_user(db, "rule_no_owner@test.com", "sales_rep")
    rep_b = await _create_user(db, "rule_no_target@test.com", "sales_rep")
    customer = Customer(
        tenant_id=_TENANT_ID,
        name="Farkli Musteri",
        email="farkli@example.com",
        company="Teknoloji Ltd",
        created_by=rep_a.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    rule = SharingRule(
        name="Sanayi Filtresi",
        entity_type="customer",
        criteria_json=json.dumps({
            "field": "company",
            "operator": "contains",
            "value": "Sanayi",
        }),
        share_with_role="sales_rep",
        access_level="read",
    )
    db.add(rule)
    await db.commit()

    service = AccessService(db)
    result = await service.can_access(
        user_id=rep_b.id,
        user_role=rep_b.role,
        entity_type="customer",
        entity_id=customer.id,
    )
    assert result is False
