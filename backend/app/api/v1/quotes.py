import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import Role, get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart
from app.models.user import User

router = APIRouter(prefix="/quotes", tags=["Quotes"])


@router.get("/")
async def list_quotes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
    customer_id: int | None = Query(None, description="Filter by customer"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List quotes with pagination and filtering."""
    query = select(Quote)
    count_query = select(func.count(Quote.id))

    conditions = []
    if status:
        conditions.append(Quote.status == status)
    if customer_id is not None:
        conditions.append(Quote.customer_id == customer_id)

    if conditions:
        combined = and_(*conditions)
        query = query.where(combined)
        count_query = count_query.where(combined)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Quote.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    quotes = result.scalars().all()

    return {
        "items": [_quote_to_dict(q, include_items=True) for q in quotes],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{quote_id}")
async def get_quote(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get quote detail with items."""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException(f"Quote with id {quote_id} not found")

    return _quote_to_dict(quote, include_items=True)


@router.post("/", status_code=201)
async def create_quote(
    data: dict,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a quote manually."""
    customer_id = data.get("customer_id")

    # Validate customer if provided
    if customer_id:
        cust_result = await db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        if not cust_result.scalar_one_or_none():
            raise NotFoundException(f"Customer with id {customer_id} not found")

    # Generate quote number
    quote_number = f"QT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    quote = Quote(
        quote_number=quote_number,
        customer_id=customer_id,
        created_by=current_user.id,
        status="draft",
        language=data.get("language", "tr"),
        currency=data.get("currency", "TRY"),
        tax_rate=float(data.get("tax_rate", 20.0)),
        valid_days=int(data.get("valid_days", 30)),
        notes=data.get("notes"),
    )
    db.add(quote)
    await db.flush()

    # Add items if provided
    items_data = data.get("items", [])
    await _create_quote_items(db, quote.id, items_data)

    # Recalculate totals
    await _recalculate_quote(db, quote)
    await db.refresh(quote)

    return _quote_to_dict(quote, include_items=True)


@router.post("/from-email/{email_id}", status_code=201)
async def create_quote_from_email(
    email_id: int,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a quote from a parsed email."""
    email_result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = email_result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"Email with id {email_id} not found")

    if email.status == "new":
        raise BadRequestException("Email has not been parsed yet")

    # Generate quote number
    quote_number = f"QT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    quote = Quote(
        quote_number=quote_number,
        customer_id=email.customer_id,
        email_request_id=email.id,
        created_by=current_user.id,
        status="draft",
        language=email.language or "tr",
    )
    db.add(quote)
    await db.flush()

    # If parsed_data contains items, create quote items from them
    if email.parsed_data:
        try:
            parsed = json.loads(email.parsed_data)
            items = parsed.get("items", [])
            for i, item in enumerate(items):
                code = item.get("honeywell_code") or item.get("code", "")
                quantity = int(item.get("quantity", 1))

                # Try to find matching spare part
                spare_part_id = None
                unit_price = 0.0
                if code:
                    part_result = await db.execute(
                        select(SparePart).where(SparePart.honeywell_code == code)
                    )
                    part = part_result.scalar_one_or_none()
                    if part:
                        spare_part_id = part.id
                        # Use first available price
                        if part.prices:
                            unit_price = part.prices[0].net_price

                line_total = quantity * unit_price

                qi = QuoteItem(
                    quote_id=quote.id,
                    spare_part_id=spare_part_id,
                    original_text=item.get("original_text", ""),
                    honeywell_code=code,
                    description=item.get("description", ""),
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                    match_score=item.get("match_score"),
                    match_strategy=item.get("match_strategy"),
                    sort_order=i,
                )
                db.add(qi)
        except (json.JSONDecodeError, KeyError):
            pass

    # Update email status
    email.status = "quoted"
    await db.flush()

    await _recalculate_quote(db, quote)
    await db.refresh(quote)

    return _quote_to_dict(quote, include_items=True)


@router.put("/{quote_id}")
async def update_quote(
    quote_id: int,
    data: dict,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update quote header and items."""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException(f"Quote with id {quote_id} not found")

    if quote.status not in ("draft", "pending_approval"):
        raise BadRequestException(
            f"Cannot edit quote in '{quote.status}' status. Only draft or pending_approval quotes can be edited."
        )

    # Update header fields
    header_fields = [
        "customer_id", "language", "currency", "tax_rate",
        "valid_days", "notes",
    ]
    for field in header_fields:
        if field in data:
            setattr(quote, field, data[field])

    # Replace items if provided
    if "items" in data:
        # Delete existing items
        existing_items = await db.execute(
            select(QuoteItem).where(QuoteItem.quote_id == quote_id)
        )
        for item in existing_items.scalars().all():
            await db.delete(item)
        await db.flush()

        # Create new items
        await _create_quote_items(db, quote_id, data["items"])

    # Recalculate totals
    await _recalculate_quote(db, quote)
    await db.refresh(quote)

    return _quote_to_dict(quote, include_items=True)


@router.patch("/{quote_id}/approve")
async def approve_quote(
    quote_id: int,
    current_user: User = Depends(require_role(Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Approve a quote and generate PDF (sales_manager only)."""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException(f"Quote with id {quote_id} not found")

    if quote.status not in ("draft", "pending_approval"):
        raise BadRequestException(
            f"Cannot approve quote in '{quote.status}' status"
        )

    quote.status = "approved"
    quote.approved_by = current_user.id

    # TODO: Generate PDF via service layer
    # pdf_path = await pdf_service.generate_quote_pdf(quote)
    # quote.pdf_path = pdf_path

    await db.flush()
    await db.refresh(quote)

    return _quote_to_dict(quote, include_items=True)


@router.post("/{quote_id}/send")
async def send_quote(
    quote_id: int,
    data: dict | None = None,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Send a quote via email."""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException(f"Quote with id {quote_id} not found")

    if quote.status not in ("approved", "sent"):
        raise BadRequestException(
            f"Quote must be approved before sending (current status: {quote.status})"
        )

    # TODO: Send email via service layer
    # await email_service.send_quote(quote, recipient_email=data.get("email"))

    quote.status = "sent"
    await db.flush()

    return {"message": f"Quote {quote.quote_number} sent successfully"}


@router.get("/{quote_id}/pdf")
async def download_quote_pdf(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download quote PDF with path traversal protection."""
    from app.core.security import is_safe_path
    from app.core.config import settings as cfg

    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException(f"Quote with id {quote_id} not found")

    # Authorization: only creator or manager can download
    if quote.created_by != current_user.id and current_user.role != "sales_manager":
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException("Bu teklifi indirme yetkiniz yok")

    if not quote.pdf_path:
        raise BadRequestException("PDF has not been generated for this quote")

    # Path traversal protection
    pdf_file = Path(quote.pdf_path)
    if not is_safe_path(cfg.QUOTES_DIR, str(pdf_file)):
        raise BadRequestException("Invalid PDF path")

    if not pdf_file.exists():
        raise NotFoundException("PDF file not found on disk")

    return FileResponse(
        path=str(pdf_file),
        media_type="application/pdf",
        filename=f"{quote.quote_number}.pdf",
    )


# ---- Helper Functions ----

async def _create_quote_items(
    db: AsyncSession, quote_id: int, items_data: list[dict]
) -> None:
    """Create QuoteItem records from a list of item dicts."""
    for i, item_data in enumerate(items_data):
        spare_part_id = item_data.get("spare_part_id")
        quantity = int(item_data.get("quantity", 1))
        unit_price = float(item_data.get("unit_price", 0.0))
        discount_pct = float(item_data.get("discount_pct", 0.0))

        # If spare_part_id given, look up code/description
        honeywell_code = item_data.get("honeywell_code")
        description = item_data.get("description")

        if spare_part_id and not honeywell_code:
            part_result = await db.execute(
                select(SparePart).where(SparePart.id == spare_part_id)
            )
            part = part_result.scalar_one_or_none()
            if part:
                honeywell_code = honeywell_code or part.honeywell_code
                description = description or part.name_en

        discounted_price = unit_price * (1 - discount_pct / 100)
        line_total = quantity * discounted_price

        qi = QuoteItem(
            quote_id=quote_id,
            spare_part_id=spare_part_id,
            original_text=item_data.get("original_text"),
            honeywell_code=honeywell_code,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            discount_pct=discount_pct,
            line_total=round(line_total, 2),
            match_score=item_data.get("match_score"),
            match_strategy=item_data.get("match_strategy"),
            is_confirmed=item_data.get("is_confirmed", False),
            sort_order=i,
        )
        db.add(qi)

    await db.flush()


async def _recalculate_quote(db: AsyncSession, quote: Quote) -> None:
    """Recalculate quote totals from items."""
    items_result = await db.execute(
        select(QuoteItem).where(QuoteItem.quote_id == quote.id)
    )
    items = items_result.scalars().all()

    subtotal = sum(item.line_total for item in items)
    tax_amount = subtotal * (quote.tax_rate / 100)
    grand_total = subtotal + tax_amount - quote.discount_total

    quote.subtotal = round(subtotal, 2)
    quote.tax_amount = round(tax_amount, 2)
    quote.grand_total = round(grand_total, 2)

    await db.flush()


def _quote_to_dict(quote: Quote, include_items: bool = False) -> dict:
    """Convert Quote to a dictionary response."""
    data = {
        "id": quote.id,
        "quote_number": quote.quote_number,
        "customer_id": quote.customer_id,
        "email_request_id": quote.email_request_id,
        "created_by": quote.created_by,
        "approved_by": quote.approved_by,
        "status": quote.status,
        "language": quote.language,
        "currency": quote.currency,
        "subtotal": quote.subtotal,
        "discount_total": quote.discount_total,
        "tax_rate": quote.tax_rate,
        "tax_amount": quote.tax_amount,
        "grand_total": quote.grand_total,
        "valid_days": quote.valid_days,
        "notes": quote.notes,
        "pdf_path": quote.pdf_path,
        "version": quote.version,
        "parent_quote_id": quote.parent_quote_id,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
        "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
        "customer": {
            "id": quote.customer.id,
            "name": quote.customer.name,
            "company": quote.customer.company,
            "email": quote.customer.email,
        } if quote.customer else None,
    }

    if include_items:
        data["items"] = [
            {
                "id": item.id,
                "spare_part_id": item.spare_part_id,
                "original_text": item.original_text,
                "honeywell_code": item.honeywell_code,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount_pct": item.discount_pct,
                "line_total": item.line_total,
                "match_score": item.match_score,
                "match_strategy": item.match_strategy,
                "is_confirmed": item.is_confirmed,
                "sort_order": item.sort_order,
                "spare_part": {
                    "id": item.spare_part.id,
                    "honeywell_code": item.spare_part.honeywell_code,
                    "name_en": item.spare_part.name_en,
                } if item.spare_part else None,
            }
            for item in (quote.items or [])
        ]

    return data
