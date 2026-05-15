"""Test fixture factories for CRM entities.

Round-15 Sprint 15k/15l unblocker (see
``docs/audits/2026-05-15-15kl-parking-notes.md`` for the parking
context). The audit's F-001 finding wants to promote ``tenant_id``
from NULLABLE to NOT NULL on the top-tier CRM tables (customers,
opportunities, quotes, leads, contracts, invoices, campaigns,
subscriptions). Promotion is blocked because ~50 test files
construct these models directly without threading ``tenant_id``.

This module provides ``make_*`` helpers that:

  1. Default ``tenant_id`` to the canonical single-tenant test value
     (``DEFAULT_TENANT_ID = 1``) — same value the existing
     ``admin_user`` fixture uses.
  2. Accept overrides for any column the test needs to customize.
  3. ``db.add`` + ``db.flush`` the row and return it ready-to-use.

The helpers are intentionally **not** pytest fixtures — they are
plain async functions. Tests can call them directly inside any test
body without rewriting their fixture signature. A test that wants the
factory wraps it like::

    customer = await make_customer(db, name="Acme")
    opp = await make_opportunity(db, customer_id=customer.id, owner_id=admin_user.id)

When Sprint 15k/15l promotes the columns to NOT NULL, every test
that switched to the factory keeps passing — the factory always
threads ``tenant_id``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.subscription import Subscription


DEFAULT_TENANT_ID: int = 1
"""Canonical single-tenant test value.

Matches ``admin_user.tenant_id`` in ``tests/conftest.py``.
"""


async def make_customer(
    db: AsyncSession,
    *,
    name: str = "Test Customer",
    email: str = "test@example.com",
    tenant_id: int = DEFAULT_TENANT_ID,
    created_by: int | None = None,
    **extra: Any,
) -> Customer:
    """Create + flush a Customer with tenant_id threaded by default.

    ``email`` must be unique across tests in the same DB session — pass
    an explicit one for parallel rows.
    """
    customer = Customer(
        name=name,
        email=email,
        tenant_id=tenant_id,
        created_by=created_by,
        **extra,
    )
    db.add(customer)
    await db.flush()
    return customer


async def make_opportunity(
    db: AsyncSession,
    *,
    owner_id: int,
    title: str = "Test Opportunity",
    stage: str = "prospecting",
    customer_id: int | None = None,
    tenant_id: int = DEFAULT_TENANT_ID,
    amount: float | None = None,
    close_date: date | None = None,
    **extra: Any,
) -> Opportunity:
    """Create + flush an Opportunity. ``owner_id`` is required (FK is NOT NULL)."""
    opp = Opportunity(
        title=title,
        stage=stage,
        owner_id=owner_id,
        customer_id=customer_id,
        tenant_id=tenant_id,
        amount=amount,
        close_date=close_date,
        **extra,
    )
    db.add(opp)
    await db.flush()
    return opp


async def make_quote(
    db: AsyncSession,
    *,
    quote_number: str,
    customer_id: int | None = None,
    created_by: int | None = None,
    opportunity_id: int | None = None,
    tenant_id: int = DEFAULT_TENANT_ID,
    status: str = "draft",
    **extra: Any,
) -> Quote:
    """Create + flush a Quote. ``quote_number`` is UNIQUE on the row."""
    quote = Quote(
        quote_number=quote_number,
        customer_id=customer_id,
        created_by=created_by,
        opportunity_id=opportunity_id,
        tenant_id=tenant_id,
        status=status,
        **extra,
    )
    db.add(quote)
    await db.flush()
    return quote


async def make_lead(
    db: AsyncSession,
    *,
    owner_id: int,
    first_name: str = "Test",
    last_name: str = "Lead",
    email: str = "lead@example.com",
    tenant_id: int = DEFAULT_TENANT_ID,
    status: str = "new",
    **extra: Any,
) -> Lead:
    """Create + flush a Lead. ``owner_id`` is required (FK is NOT NULL)."""
    lead = Lead(
        first_name=first_name,
        last_name=last_name,
        email=email,
        owner_id=owner_id,
        tenant_id=tenant_id,
        status=status,
        **extra,
    )
    db.add(lead)
    await db.flush()
    return lead


async def make_contract(
    db: AsyncSession,
    *,
    customer_id: int,
    created_by: int,
    title: str = "Test Contract",
    tenant_id: int = DEFAULT_TENANT_ID,
    status: str = "draft",
    **extra: Any,
) -> Contract:
    """Create + flush a Contract."""
    contract = Contract(
        title=title,
        customer_id=customer_id,
        created_by=created_by,
        tenant_id=tenant_id,
        status=status,
        **extra,
    )
    db.add(contract)
    await db.flush()
    return contract


async def make_invoice(
    db: AsyncSession,
    *,
    customer_id: int,
    created_by: int,
    invoice_number: str,
    tenant_id: int = DEFAULT_TENANT_ID,
    status: str = "draft",
    **extra: Any,
) -> Invoice:
    """Create + flush an Invoice. ``invoice_number`` is UNIQUE."""
    invoice = Invoice(
        invoice_number=invoice_number,
        customer_id=customer_id,
        created_by=created_by,
        tenant_id=tenant_id,
        status=status,
        **extra,
    )
    db.add(invoice)
    await db.flush()
    return invoice


async def make_subscription(
    db: AsyncSession,
    *,
    customer_id: int,
    created_by: int,
    name: str = "Test Subscription",
    tenant_id: int = DEFAULT_TENANT_ID,
    status: str = "active",
    start_date: date | None = None,
    **extra: Any,
) -> Subscription:
    """Create + flush a Subscription.

    ``start_date`` is required on the schema (``Subscription.start_date``
    is NOT NULL); the factory defaults to today's UTC date when the
    caller doesn't specify.
    """
    subscription = Subscription(
        name=name,
        customer_id=customer_id,
        created_by=created_by,
        tenant_id=tenant_id,
        status=status,
        start_date=start_date if start_date is not None else date.today(),
        **extra,
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def make_campaign(
    db: AsyncSession,
    *,
    created_by: int,
    name: str = "Test Campaign",
    type: str = "email",
    status: str = "draft",
    tenant_id: int = DEFAULT_TENANT_ID,
    start_date: datetime | None = None,
    **extra: Any,
) -> Campaign:
    """Create + flush a Campaign."""
    campaign = Campaign(
        name=name,
        type=type,
        status=status,
        created_by=created_by,
        tenant_id=tenant_id,
        start_date=start_date,
        **extra,
    )
    db.add(campaign)
    await db.flush()
    return campaign


# Convenience tuple for the "all factories" registry — used by the
# sweep test that asserts every factory still threads tenant_id.
ALL_FACTORIES = (
    make_customer,
    make_opportunity,
    make_quote,
    make_lead,
    make_contract,
    make_invoice,
    make_subscription,
    make_campaign,
)


def _factory_threads_tenant_id_sentinel() -> None:
    """Sentinel for grep-based audits.

    Tests that still call ``Customer(...)`` / ``Opportunity(...)`` /
    etc. directly without ``tenant_id`` will block Sprint 15k/l.
    See ``docs/audits/2026-05-15-15kl-parking-notes.md`` for the
    migration plan.
    """
    return None


def _utc_now() -> datetime:
    """Test-friendly UTC clock helper."""
    return datetime.now(timezone.utc)
