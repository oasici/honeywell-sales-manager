"""Contract Lifecycle API endpoints."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.contract import Contract, ContractAmendment
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.contract import ContractResponse
from app.services.tenant_context import assert_same_tenant, scoped_for_user


def _require_contracts() -> None:
    """Round-5 R5-FLAG-15 — gate the entire router behind FEATURE_CONTRACTS.
    Pre-R5 the SPA could create / list / mutate contract rows even when
    the feature was operationally off."""
    if not settings.FEATURE_CONTRACTS:
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(tags=["Contracts"], dependencies=[Depends(_require_contracts)])

VALID_STATUSES = {"draft", "active", "amended", "expired", "terminated"}
VALID_AMENDMENT_TYPES = {"extension", "modification", "termination"}


class ContractCreate(BaseModel):
    customer_id: int
    quote_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    value: float | None = None
    terms_json: str | None = None


class ContractUpdate(BaseModel):
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    value: float | None = None
    terms_json: str | None = None
    status: str | None = None


class AmendmentCreate(BaseModel):
    amendment_type: str
    changes_json: str | None = None
    effective_date: date | None = None


def _serialize_contract(c: Contract) -> dict:
    # R5-RENDER-CONTRACT-1 — list/detail endpoints used to omit the
    # customer object entirely, so the contract list rendered "—" or
    # "#${customer_id}" in the customer column. Mirrors the R5-API-1
    # invoice fix; selectin relationship makes this free.
    customer_summary: dict | None = None
    if getattr(c, "customer", None) is not None:
        customer_summary = {
            "id": c.customer.id,
            "name": c.customer.name,
            "company": c.customer.company,
        }
    data = {
        "id": c.id,
        # Round-4 R4-DTO-6 — round-trip tenant_id (R4-TEN-6).
        "tenant_id": getattr(c, "tenant_id", None),
        "customer_id": c.customer_id,
        "customer": customer_summary,
        "quote_id": c.quote_id,
        "title": c.title,
        "status": c.status,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "value": c.value,
        "terms_json": c.terms_json,
        "signed_at": c.signed_at.isoformat() if c.signed_at else None,
        "signed_by": c.signed_by,
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "amendments": [
            {
                "id": a.id,
                "amendment_type": a.amendment_type,
                "changes_json": a.changes_json,
                "effective_date": a.effective_date.isoformat() if a.effective_date else None,
                "approved_by": a.approved_by,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in (c.amendments or [])
        ],
    }
    # R5-PERM-1 — admin-configured field-permission rules apply here
    # (was previously dead code on contract because the helper was
    # never called from this serializer).
    from app.services.field_permission_service import apply_request_perms

    return apply_request_perms(data, "contract")


# Round-10 R10-API-5 — canonical pagination envelope on OpenAPI.
@router.get("/contracts/", response_model=PaginatedResponse[ContractResponse])
async def list_contracts(
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List contracts with optional filters.

    Audit A-6: previously returned ``{"contracts": [...]}`` with no
    pagination at all. Standardized to the canonical envelope so the
    frontend list component doesn't need a contracts-specific shape,
    and bounded by page_size to prevent unbounded list responses.
    """
    from sqlalchemy import func as _func
    import math as _math

    query = scoped_for_user(
        select(Contract).order_by(Contract.created_at.desc()),
        current_user,
        column=Contract.tenant_id,
    )
    if customer_id:
        query = query.where(Contract.customer_id == customer_id)
    if status:
        query = query.where(Contract.status == status)
    if search:
        query = query.where(Contract.title.ilike(f"%{search}%"))

    count_result = await db.execute(
        select(_func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    contracts = result.scalars().all()

    return {
        "items": [_serialize_contract(c) for c in contracts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/contracts/", status_code=201, response_model=ContractResponse)
async def create_contract(
    body: ContractCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new contract."""
    contract = Contract(
        tenant_id=getattr(current_user, "tenant_id", None),
        customer_id=body.customer_id,
        quote_id=body.quote_id,
        title=body.title,
        start_date=body.start_date,
        end_date=body.end_date,
        value=body.value,
        terms_json=body.terms_json,
        created_by=current_user.id,
    )
    db.add(contract)
    await db.flush()
    await db.refresh(contract)
    return _serialize_contract(contract)


@router.get("/contracts/expiring", response_model=PaginatedResponse[ContractResponse])
async def expiring_contracts(
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get contracts expiring within the next N days.

    Round-5 Phase 7 — standardized to canonical pagination envelope
    ``{items,total,page,page_size,pages}`` so the SPA list components
    don't need a contracts-specific shape. ``count`` is preserved
    additively for any in-flight consumers.
    """
    from sqlalchemy import func as _func
    import math as _math

    threshold = date.today() + timedelta(days=days)
    base_query = (
        scoped_for_user(
            select(Contract), current_user, column=Contract.tenant_id
        )
        .where(
            Contract.status == "active",
            Contract.end_date.isnot(None),
            Contract.end_date <= threshold,
            Contract.end_date >= date.today(),
        )
        .order_by(Contract.end_date.asc())
    )

    count_result = await db.execute(
        select(_func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(base_query.offset(offset).limit(page_size))
    contracts = result.scalars().all()

    return {
        "items": [_serialize_contract(c) for c in contracts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
        # Additive legacy keys to ease in-flight rollout.
        "contracts": [_serialize_contract(c) for c in contracts],
        "count": total,
    }


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get contract detail with amendments."""
    contract = await db.get(Contract, contract_id)
    if not contract:
        raise NotFoundException("Kontrat bulunamadi")
    assert_same_tenant(contract, current_user, exception_cls=NotFoundException)
    return _serialize_contract(contract)


@router.put("/contracts/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: int,
    body: ContractUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update contract fields."""
    contract = await db.get(Contract, contract_id)
    if not contract:
        raise NotFoundException("Kontrat bulunamadi")
    assert_same_tenant(contract, current_user, exception_cls=NotFoundException)

    if body.title is not None:
        contract.title = body.title
    if body.start_date is not None:
        contract.start_date = body.start_date
    if body.end_date is not None:
        contract.end_date = body.end_date
    if body.value is not None:
        contract.value = body.value
    if body.terms_json is not None:
        contract.terms_json = body.terms_json
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise BadRequestException(f"Gecersiz durum: {body.status}")
        contract.status = body.status

    await db.flush()
    await db.refresh(contract)
    return _serialize_contract(contract)


@router.post("/contracts/{contract_id}/amend", response_model=dict)
async def amend_contract(
    contract_id: int,
    body: AmendmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an amendment for a contract."""
    contract = await db.get(Contract, contract_id)
    if not contract:
        raise NotFoundException("Kontrat bulunamadi")
    assert_same_tenant(contract, current_user, exception_cls=NotFoundException)

    if body.amendment_type not in VALID_AMENDMENT_TYPES:
        raise BadRequestException(f"Gecersiz degisiklik tipi: {body.amendment_type}")

    amendment = ContractAmendment(
        contract_id=contract_id,
        amendment_type=body.amendment_type,
        changes_json=body.changes_json,
        effective_date=body.effective_date,
        approved_by=current_user.id,
    )
    db.add(amendment)

    if contract.status == "active":
        contract.status = "amended"

    await db.flush()
    await db.refresh(amendment)
    return {
        "id": amendment.id,
        "amendment_type": amendment.amendment_type,
        "contract_status": contract.status,
    }


@router.post("/contracts/{contract_id}/activate", response_model=dict)
async def activate_contract(
    contract_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate a draft contract."""
    contract = await db.get(Contract, contract_id)
    if not contract:
        raise NotFoundException("Kontrat bulunamadi")
    assert_same_tenant(contract, current_user, exception_cls=NotFoundException)

    if contract.status != "draft":
        raise BadRequestException("Sadece taslak kontratlar aktiflestirebilir")

    contract.status = "active"
    contract.signed_at = datetime.now(timezone.utc)
    contract.signed_by = current_user.full_name if hasattr(current_user, "full_name") else str(current_user.id)

    await db.flush()
    await db.refresh(contract)
    return _serialize_contract(contract)
