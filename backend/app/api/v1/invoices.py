"""Invoice Management API — CRUD, status transitions, and quote-to-invoice conversion."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.invoice import Invoice
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.user import User

router = APIRouter(prefix="/invoices", tags=["Invoices"])

PAYMENT_TERMS_DAYS = 30

VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["sent", "voided"],
    "sent": ["paid", "overdue", "voided"],
    "paid": ["voided"],
    "overdue": ["paid", "voided"],
    "voided": [],
}


def _require_invoicing():
    """Dependency: reject if FEATURE_INVOICING is off."""
    if not settings.FEATURE_INVOICING:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class InvoiceCreate(BaseModel):
    customer_id: int
    quote_id: Optional[int] = None
    contract_id: Optional[int] = None
    currency: str = Field(default="TRY", max_length=10)
    subtotal: float = Field(default=0.0, ge=0)
    tax_rate: float = Field(default=18.0, ge=0)
    items_json: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[datetime] = None


class InvoiceUpdate(BaseModel):
    currency: Optional[str] = Field(default=None, max_length=10)
    subtotal: Optional[float] = Field(default=None, ge=0)
    tax_rate: Optional[float] = Field(default=None, ge=0)
    items_json: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[datetime] = None
    contract_id: Optional[int] = None


class StatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=20)


# ── Helpers ──


def _compute_totals(subtotal: float, tax_rate: float) -> tuple[float, float]:
    """Return (tax_amount, grand_total)."""
    tax_amount = round(subtotal * tax_rate / 100, 2)
    grand_total = round(subtotal + tax_amount, 2)
    return tax_amount, grand_total


def _invoice_to_dict(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "quote_id": invoice.quote_id,
        "contract_id": invoice.contract_id,
        "customer_id": invoice.customer_id,
        "created_by": invoice.created_by,
        "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "status": invoice.status,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "tax_rate": invoice.tax_rate,
        "tax_amount": invoice.tax_amount,
        "grand_total": invoice.grand_total,
        "items_json": invoice.items_json,
        "notes": invoice.notes,
        "pdf_path": invoice.pdf_path,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None,
    }


async def _generate_invoice_number(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    result = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.invoice_number.like(f"INV-{year}-%")
        )
    )
    count = result.scalar_one()
    return f"INV-{year}-{count + 1:04d}"


# ── Endpoints ──


@router.get("/")
async def list_invoices(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_invoicing),
):
    """List invoices with optional status/customer filters and pagination."""
    query = select(Invoice).order_by(Invoice.created_at.desc())
    if status:
        query = query.where(Invoice.status == status)
    if customer_id:
        query = query.where(Invoice.customer_id == customer_id)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(query.offset(skip).limit(limit))
    invoices = result.scalars().all()

    return {
        "items": [_invoice_to_dict(inv) for inv in invoices],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/", status_code=201)
async def create_invoice(
    body: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_invoicing),
):
    """Create a new invoice."""
    invoice_number = await _generate_invoice_number(db)
    tax_amount, grand_total = _compute_totals(body.subtotal, body.tax_rate)

    invoice = Invoice(
        invoice_number=invoice_number,
        customer_id=body.customer_id,
        quote_id=body.quote_id,
        contract_id=body.contract_id,
        currency=body.currency,
        subtotal=body.subtotal,
        tax_rate=body.tax_rate,
        tax_amount=tax_amount,
        grand_total=grand_total,
        items_json=body.items_json,
        notes=body.notes,
        due_date=body.due_date,
        created_by=current_user.id,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return {
        "message": "Fatura olusturuldu",
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
    }


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_invoicing),
):
    """Get invoice detail."""
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura bulunamadi")
    return _invoice_to_dict(invoice)


@router.put("/{invoice_id}")
async def update_invoice(
    invoice_id: int,
    body: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_invoicing),
):
    """Update an invoice (only allowed in draft status)."""
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura bulunamadi")
    if invoice.status != "draft":
        raise HTTPException(status_code=400, detail="Yalnizca taslak faturalar guncellenebilir")

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Guncellenecek alan bulunamadi")

    for key, value in update_data.items():
        setattr(invoice, key, value)

    # Recompute totals if financial fields changed
    invoice.tax_amount, invoice.grand_total = _compute_totals(invoice.subtotal, invoice.tax_rate)

    await db.commit()
    await db.refresh(invoice)
    return {"message": "Fatura guncellendi", "id": invoice.id}


@router.patch("/{invoice_id}/status")
async def update_invoice_status(
    invoice_id: int,
    body: StatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_invoicing),
):
    """Transition invoice status with validation."""
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura bulunamadi")

    allowed = VALID_TRANSITIONS.get(invoice.status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"'{invoice.status}' durumundan '{body.status}' durumuna gecis yapilamaz",
        )

    now = datetime.now(timezone.utc)

    if body.status == "sent":
        invoice.issue_date = now
        if not invoice.due_date:
            invoice.due_date = now + timedelta(days=PAYMENT_TERMS_DAYS)

    if body.status == "paid":
        invoice.paid_at = now

    invoice.status = body.status
    await db.commit()
    await db.refresh(invoice)
    return {"message": "Fatura durumu guncellendi", "id": invoice_id, "status": body.status}


@router.post("/from-quote/{quote_id}", status_code=201)
async def create_invoice_from_quote(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_invoicing),
):
    """Create an invoice by copying line items from an existing quote."""
    quote_result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = quote_result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Teklif bulunamadi")

    if quote.status not in ("accepted", "approved", "sent"):
        raise HTTPException(
            status_code=400,
            detail="Quote must be accepted or approved before invoicing",
        )

    items_result = await db.execute(
        select(QuoteItem).where(QuoteItem.quote_id == quote_id)
    )
    quote_items = items_result.scalars().all()

    items_data = [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "total": item.line_total,
        }
        for item in quote_items
    ]

    subtotal = sum(item.get("total", 0.0) for item in items_data)
    tax_rate = quote.tax_rate
    tax_amount, grand_total = _compute_totals(subtotal, tax_rate)

    invoice_number = await _generate_invoice_number(db)

    invoice = Invoice(
        invoice_number=invoice_number,
        quote_id=quote_id,
        customer_id=quote.customer_id,
        currency=quote.currency,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        grand_total=grand_total,
        items_json=json.dumps(items_data),
        created_by=current_user.id,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return {
        "message": "Tekliften fatura olusturuldu",
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "quote_id": quote_id,
    }
