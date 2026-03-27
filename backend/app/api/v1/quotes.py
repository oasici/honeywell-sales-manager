import math
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.enums import UserRole
from app.models.quote import Quote
from app.models.user import User
from app.schemas.quote import QuoteCreate, QuoteUpdate
from app.services.quote_service import QuoteService

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
    data: QuoteCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a quote manually."""
    service = QuoteService(db)
    quote = await service.create_quote(
        customer_id=data.customer_id,
        items=[item.model_dump() for item in data.items],
        language=data.language,
        currency=data.currency,
        tax_rate=data.tax_rate,
        notes=data.notes,
        created_by=current_user.id,
    )

    return _quote_to_dict(quote, include_items=True)


@router.post("/from-email/{email_id}", status_code=201)
async def create_quote_from_email(
    email_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a quote from a parsed email."""
    service = QuoteService(db)
    quote = await service.create_quote_from_email(
        email_id=email_id,
        created_by=current_user.id,
    )

    return _quote_to_dict(quote, include_items=True)


@router.put("/{quote_id}")
async def update_quote(
    quote_id: int,
    data: QuoteUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update quote header and items."""
    payload = data.model_dump(exclude_unset=True)
    items = None
    if "items" in payload and payload["items"] is not None:
        items = payload.pop("items")

    service = QuoteService(db)
    quote = await service.update_quote(
        quote_id=quote_id,
        data=payload,
        items=items,
    )

    return _quote_to_dict(quote, include_items=True)


@router.patch("/{quote_id}/approve")
async def approve_quote(
    quote_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Approve a quote and generate PDF (sales_manager only)."""
    service = QuoteService(db)
    quote = await service.approve_quote(
        quote_id=quote_id,
        approved_by=current_user.id,
    )

    return _quote_to_dict(quote, include_items=True)


@router.post("/{quote_id}/send")
async def send_quote(
    quote_id: int,
    data: dict | None = None,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
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
    if quote.created_by != current_user.id and current_user.role != UserRole.SALES_MANAGER.value:
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
