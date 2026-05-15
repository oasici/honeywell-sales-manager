"""Proves every CRM factory in ``tests/factories.py`` threads tenant_id.

Round-15 Sprint 15k/l unblocker. The audit's F-001 NOT-NULL
promotion is parked because per-test constructors don't thread
``tenant_id``. The new factories in ``tests/factories.py`` always
do — this test pins that behavior so a future PR that "simplifies"
a factory by dropping the default tenant_id flag trips CI.

If you add a new factory, append it to ``ALL_FACTORIES`` in
``factories.py`` and add a per-factory ``test_*_threads_tenant_id``
below using the same shape.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.core.security import hash_password
from tests.factories import (
    DEFAULT_TENANT_ID,
    make_campaign,
    make_contract,
    make_customer,
    make_invoice,
    make_lead,
    make_opportunity,
    make_quote,
    make_subscription,
)


@pytest_asyncio.fixture
async def factory_user(db: AsyncSession) -> User:
    """Lightweight User row for tests that need a creator/owner FK.

    Distinct from the conftest ``admin_user`` fixture so this file is
    self-contained.
    """
    user = User(
        tenant_id=DEFAULT_TENANT_ID,
        email="factory-user@test.local",
        full_name="Factory User",
        hashed_password=hash_password("test123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_make_customer_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    customer = await make_customer(
        db,
        name="Factory Test Co",
        email="factory-customer@test.local",
        created_by=factory_user.id,
    )
    assert customer.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_opportunity_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    customer = await make_customer(
        db,
        name="Opp Parent Co",
        email="opp-parent@test.local",
        created_by=factory_user.id,
    )
    opp = await make_opportunity(
        db,
        owner_id=factory_user.id,
        customer_id=customer.id,
        title="Factory Opp",
    )
    assert opp.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_quote_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    customer = await make_customer(
        db,
        name="Quote Parent Co",
        email="quote-parent@test.local",
        created_by=factory_user.id,
    )
    quote = await make_quote(
        db,
        quote_number="Q-FACTORY-001",
        customer_id=customer.id,
        created_by=factory_user.id,
    )
    assert quote.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_lead_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    lead = await make_lead(
        db,
        owner_id=factory_user.id,
        email="factory-lead@test.local",
    )
    assert lead.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_contract_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    customer = await make_customer(
        db,
        name="Contract Parent Co",
        email="contract-parent@test.local",
        created_by=factory_user.id,
    )
    contract = await make_contract(
        db,
        customer_id=customer.id,
        created_by=factory_user.id,
    )
    assert contract.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_invoice_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    customer = await make_customer(
        db,
        name="Invoice Parent Co",
        email="invoice-parent@test.local",
        created_by=factory_user.id,
    )
    invoice = await make_invoice(
        db,
        customer_id=customer.id,
        created_by=factory_user.id,
        invoice_number="INV-FACTORY-001",
    )
    assert invoice.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_subscription_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    customer = await make_customer(
        db,
        name="Sub Parent Co",
        email="sub-parent@test.local",
        created_by=factory_user.id,
    )
    subscription = await make_subscription(
        db,
        customer_id=customer.id,
        created_by=factory_user.id,
    )
    assert subscription.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_make_campaign_threads_tenant_id(
    db: AsyncSession, factory_user: User
) -> None:
    campaign = await make_campaign(
        db,
        created_by=factory_user.id,
        name="Factory Campaign",
    )
    assert campaign.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.asyncio
async def test_override_tenant_id_is_respected(
    db: AsyncSession, factory_user: User
) -> None:
    """A test that needs a non-default tenant can override the kwarg."""
    customer = await make_customer(
        db,
        name="Tenant-99 Customer",
        email="t99@test.local",
        tenant_id=99,
        created_by=factory_user.id,
    )
    assert customer.tenant_id == 99
