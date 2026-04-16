import math
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.enums import UserRole
from app.models.quote import Quote
from app.models.user import User
from app.schemas.quote import QuoteCreate, QuoteUpdate
from app.core.event_bus import event_bus
from app.services.activity_logger import log_activity
from app.services.notification_service import create_notification
from app.services.quote_service import QuoteService

router = APIRouter(prefix="/quotes", tags=["Quotes"])


@router.get("/")
async def list_quotes(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
    customer_id: int | None = Query(None, description="Filter by customer"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List quotes with pagination and filtering."""
    from sqlalchemy.orm import selectinload

    query = select(Quote).options(selectinload(Quote.customer), selectinload(Quote.items))
    count_query = select(func.count(Quote.id))

    conditions = []
    # Ownership scoping: non-managers see only their own quotes
    if current_user.role != UserRole.SALES_MANAGER.value:
        conditions.append(Quote.created_by == current_user.id)
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
    quotes = result.scalars().unique().all()

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
    """Get quote detail with items. Non-managers can only see their own quotes."""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException("Teklif bulunamadi")

    # Ownership check: non-managers can only access their own quotes
    if current_user.role != UserRole.SALES_MANAGER.value and quote.created_by != current_user.id:
        raise ForbiddenException("Bu teklife erisim yetkiniz yok")

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

    await log_activity(
        db, activity_type="quote_created", entity_type="quote", entity_id=quote.id,
        opportunity_id=quote.opportunity_id, customer_id=quote.customer_id,
        user_id=current_user.id, summary=f"Teklif olusturuldu: {quote.quote_number}",
    )

    return _quote_to_dict(quote, include_items=True)


@router.post("/from-pdf", status_code=201)
async def create_quote_from_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a draft quote by extracting data from a Honeywell PDF."""
    import tempfile
    import os

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise BadRequestException("Sadece PDF dosyasi kabul edilir")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise BadRequestException("PDF dosya boyutu 10MB'i asamaz")
    if content[:4] != b'%PDF':
        raise BadRequestException("Gecerli bir PDF dosyasi degil")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        import asyncio
        from app.services.pdf_import_service import extract_quote_data_from_pdf

        pdf_data = await asyncio.to_thread(extract_quote_data_from_pdf, tmp_path)
    finally:
        os.unlink(tmp_path)

    if not pdf_data.get("items"):
        raise BadRequestException("PDF'de malzeme listesi bulunamadi")

    # Find or create customer
    customer_id = None
    if pdf_data.get("customer_email") or pdf_data.get("customer_name"):
        from app.models.customer import Customer

        if pdf_data.get("customer_email"):
            result = await db.execute(
                select(Customer).where(Customer.email == pdf_data["customer_email"])
            )
            customer = result.scalar_one_or_none()
            if customer:
                customer_id = customer.id

        if not customer_id and pdf_data.get("customer_name"):
            new_customer = Customer(
                name=pdf_data["customer_name"],
                company=pdf_data.get("customer_company", ""),
                email=pdf_data.get("customer_email", ""),
                phone=pdf_data.get("customer_phone", ""),
                address=pdf_data.get("customer_address", ""),
                created_by=current_user.id,
            )
            db.add(new_customer)
            await db.flush()
            customer_id = new_customer.id

    # Create quote
    service = QuoteService(db)
    quote = await service.create_quote(
        customer_id=customer_id or 0,
        created_by=current_user.id,
        currency=pdf_data.get("currency", "USD"),
        items=pdf_data["items"],
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
    # Ownership check
    existing = (await db.execute(select(Quote).where(Quote.id == quote_id))).scalar_one_or_none()
    if not existing:
        raise NotFoundException("Teklif bulunamadi")
    if current_user.role != UserRole.SALES_MANAGER.value and existing.created_by != current_user.id:
        raise ForbiddenException("Bu teklifi guncelleme yetkiniz yok")

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

    await log_activity(
        db, activity_type="quote_approved", entity_type="quote", entity_id=quote.id,
        opportunity_id=quote.opportunity_id, customer_id=quote.customer_id,
        user_id=current_user.id, summary=f"Teklif onaylandi: {quote.quote_number}",
    )
    await event_bus.publish("quote.approved", {
        "quote_id": quote.id, "quote_number": quote.quote_number,
        "customer_id": quote.customer_id, "grand_total": quote.grand_total,
        "approved_by": current_user.id,
    })

    # Best-effort notification to quote creator
    if quote.created_by and quote.created_by != current_user.id:
        try:
            await create_notification(
                db, user_id=quote.created_by, type="quote_approved",
                title="Teklif onaylandi",
                message=f"{quote.quote_number} onaylandi ve PDF olusturuldu.",
                entity_type="quote", entity_id=quote.id,
            )
        except Exception:
            pass

    return _quote_to_dict(quote, include_items=True)


class SendQuoteRequest(BaseModel):
    email: str | None = None
    message: str | None = None


@router.post("/{quote_id}/send")
async def send_quote(
    quote_id: int,
    data: SendQuoteRequest | None = None,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Send a quote via email."""
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException("Teklif bulunamadi")

    # Ownership check
    if current_user.role != UserRole.SALES_MANAGER.value and quote.created_by != current_user.id:
        raise ForbiddenException("Bu teklifi gonderme yetkiniz yok")

    if quote.status not in ("approved", "sent"):
        raise BadRequestException(
            f"Teklif gonderilmeden once onaylanmalidir (mevcut durum: {quote.status})"
        )

    # Determine recipient email
    recipient = data.email if data and data.email else None
    if not recipient and quote.customer:
        recipient = quote.customer.email
    if not recipient:
        raise BadRequestException("Alici email adresi bulunamadi")

    # Regenerate PDF if missing
    from app.services.quote_generator import generate_quote_pdf
    from pathlib import Path as _Path

    pdf_path = quote.pdf_path
    if not pdf_path or not _Path(pdf_path).exists():
        service = QuoteService(db)
        quote_data = await service._build_quote_data(quote, quote.approved_by or quote.created_by)
        pdf_path = await generate_quote_pdf(quote_data, quote.language)
        quote.pdf_path = pdf_path

    # Render email body from template
    from jinja2 import Environment, FileSystemLoader
    from app.core.config import settings as cfg

    templates_dir = _Path(cfg.TEMPLATES_DIR)
    lang = quote.language or "tr"
    tpl_file = f"quote_email_{lang}.html"
    if not (templates_dir / tpl_file).exists():
        tpl_file = "quote_email_tr.html"

    customer_name = quote.customer.name if quote.customer else ""
    email_body = f"<p>Sayin {customer_name},</p><p>Teklifiniz ekte yer almaktadir.</p><p>Teklif No: {quote.quote_number}</p>"
    if (templates_dir / tpl_file).exists():
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        template = env.get_template(tpl_file)
        email_body = template.render(
            company_name=cfg.COMPANY_NAME,
            customer_name=customer_name,
            quote_number=quote.quote_number,
            grand_total=quote.grand_total,
            currency=quote.currency,
            valid_days=quote.valid_days,
            company_phone=cfg.COMPANY_PHONE,
        )

    # Send email
    from app.services.email_sender import send_quote_email

    subject = f"Teklif: {quote.quote_number} - {cfg.COMPANY_NAME}"
    success = await send_quote_email(
        to_address=recipient,
        subject=subject,
        body_html=email_body,
        pdf_path=pdf_path,
    )

    if not success:
        raise BadRequestException(
            "Email gonderilemedi. SMTP veya Graph API ayarlarinizi kontrol edin."
        )

    quote.status = "sent"
    await db.flush()

    await log_activity(
        db, activity_type="quote_sent", entity_type="quote", entity_id=quote.id,
        opportunity_id=quote.opportunity_id, customer_id=quote.customer_id,
        user_id=current_user.id, summary=f"Teklif gonderildi: {quote.quote_number} → {recipient}",
    )
    await event_bus.publish("quote.sent", {
        "quote_id": quote.id, "quote_number": quote.quote_number,
        "recipient": recipient, "customer_id": quote.customer_id,
    })

    # Best-effort notification
    if quote.created_by:
        try:
            await create_notification(
                db, user_id=quote.created_by, type="quote_sent",
                title="Teklif gonderildi",
                message=f"{quote.quote_number} → {recipient}",
                entity_type="quote", entity_id=quote.id,
            )
        except Exception:
            pass

    return {"message": f"Teklif {quote.quote_number} basariyla gonderildi: {recipient}"}


@router.get("/{quote_id}/pdf")
async def download_quote_pdf(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download quote PDF — regenerates on-the-fly if file is missing."""
    from app.core.security import is_safe_path
    from app.core.config import settings as cfg

    result = await db.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException("Teklif bulunamadi")

    # Authorization: only creator or manager can download
    if quote.created_by != current_user.id and current_user.role != UserRole.SALES_MANAGER.value:
        raise ForbiddenException("Bu teklifi indirme yetkiniz yok")

    # Regenerate PDF if file is missing (ephemeral filesystem on Render)
    pdf_file = Path(quote.pdf_path) if quote.pdf_path else None
    needs_regeneration = not pdf_file or not pdf_file.exists()

    if needs_regeneration:
        try:
            from app.services.quote_generator import generate_quote_pdf

            service = QuoteService(db)
            quote_data = await service._build_quote_data(quote, quote.approved_by or quote.created_by)
            pdf_path = await generate_quote_pdf(quote_data, quote.language)
            quote.pdf_path = pdf_path
            await db.flush()
            pdf_file = Path(pdf_path)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("PDF generation failed for quote %s: %s", quote_id, exc)
            raise BadRequestException("PDF olusturma basarisiz oldu. Lutfen tekrar deneyin.")

    # Path traversal protection
    if not is_safe_path(cfg.QUOTES_DIR, str(pdf_file)):
        raise BadRequestException("Invalid PDF path")

    if not pdf_file.exists():
        raise NotFoundException("PDF dosyasi diskte bulunamadi")

    return FileResponse(
        path=str(pdf_file),
        media_type="application/pdf",
        filename=f"{quote.quote_number}.pdf",
    )


class ConvertCurrencyRequest(BaseModel):
    target_currency: str


@router.post("/{quote_id}/convert-currency")
async def convert_quote_currency(
    quote_id: int,
    data: ConvertCurrencyRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Re-price all items in a quote to target currency using exchange rates."""
    from app.models.quote_item import QuoteItem
    from app.services.currency_service import convert_currency

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException("Teklif bulunamadi")

    if current_user.role != UserRole.SALES_MANAGER.value and quote.created_by != current_user.id:
        raise ForbiddenException("Bu teklifi guncelleme yetkiniz yok")

    target = data.target_currency.upper()
    source = quote.currency.upper()

    if source == target:
        raise BadRequestException(f"Teklif zaten {target} para biriminde")

    if quote.status not in ("draft", "pending_approval"):
        raise BadRequestException(
            f"Sadece taslak veya onay bekleyen teklifler donusturulebilir (mevcut: {quote.status})"
        )

    try:
        # Convert each item
        for item in quote.items:
            new_price = await convert_currency(item.unit_price, source, target)
            item.unit_price = new_price
            item.line_total = round(
                new_price * item.quantity * (1 - item.discount_pct / 100), 2
            )

        # Recalculate totals
        subtotal = sum(item.line_total for item in quote.items)
        quote.subtotal = round(subtotal, 2)
        quote.discount_total = round(
            await convert_currency(quote.discount_total, source, target), 2
        )
        quote.tax_amount = round(quote.subtotal * quote.tax_rate / 100, 2)
        quote.grand_total = round(quote.subtotal - quote.discount_total + quote.tax_amount, 2)
        quote.currency = target
        await db.flush()

    except ValueError as exc:
        raise BadRequestException(str(exc))

    return _quote_to_dict(quote, include_items=True)


@router.get("/{quote_id}/versions")
async def get_quote_versions(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns all versions in the chain (follow parent_quote_id links)."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise NotFoundException("Teklif bulunamadi")

    if current_user.role != UserRole.SALES_MANAGER.value and quote.created_by != current_user.id:
        raise ForbiddenException("Bu teklife erisim yetkiniz yok")

    # Walk up to root
    root_id = quote.id
    current = quote
    visited = {current.id}
    while current.parent_quote_id is not None:
        if current.parent_quote_id in visited:
            break
        visited.add(current.parent_quote_id)
        parent_result = await db.execute(
            select(Quote).where(Quote.id == current.parent_quote_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            break
        root_id = parent.id
        current = parent

    # Get all quotes in chain starting from root
    all_quotes = []
    queue = [root_id]
    seen = set()
    while queue:
        qid = queue.pop(0)
        if qid in seen:
            continue
        seen.add(qid)
        q_result = await db.execute(select(Quote).where(Quote.id == qid))
        q = q_result.scalar_one_or_none()
        if q:
            all_quotes.append(q)
            # Find children
            children_result = await db.execute(
                select(Quote.id).where(Quote.parent_quote_id == qid)
            )
            for (child_id,) in children_result.all():
                queue.append(child_id)

    all_quotes.sort(key=lambda q: q.version)

    return {
        "quote_id": quote_id,
        "versions": [
            {
                "id": q.id,
                "quote_number": q.quote_number,
                "version": q.version,
                "status": q.status,
                "grand_total": q.grand_total,
                "currency": q.currency,
                "parent_quote_id": q.parent_quote_id,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in all_quotes
        ],
    }


@router.get("/{quote_id}/compare/{other_id}")
async def compare_quotes(
    quote_id: int,
    other_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare two quotes: added, removed, changed items and summary diff."""
    result_a = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote_a = result_a.scalar_one_or_none()
    if not quote_a:
        raise NotFoundException(f"Teklif {quote_id} bulunamadi")

    result_b = await db.execute(select(Quote).where(Quote.id == other_id))
    quote_b = result_b.scalar_one_or_none()
    if not quote_b:
        raise NotFoundException(f"Teklif {other_id} bulunamadi")

    # Authorization check
    for q in (quote_a, quote_b):
        if current_user.role != UserRole.SALES_MANAGER.value and q.created_by != current_user.id:
            raise ForbiddenException(f"Teklif {q.id}'e erisim yetkiniz yok")

    # Build item maps by honeywell_code (or spare_part_id fallback)
    def _item_key(item):
        return item.honeywell_code or f"sp_{item.spare_part_id}" or f"idx_{item.sort_order}"

    items_a = {_item_key(i): i for i in (quote_a.items or [])}
    items_b = {_item_key(i): i for i in (quote_b.items or [])}

    keys_a = set(items_a.keys())
    keys_b = set(items_b.keys())

    added_items = [
        {"key": k, "description": items_b[k].description, "quantity": items_b[k].quantity, "unit_price": items_b[k].unit_price}
        for k in (keys_b - keys_a)
    ]
    removed_items = [
        {"key": k, "description": items_a[k].description, "quantity": items_a[k].quantity, "unit_price": items_a[k].unit_price}
        for k in (keys_a - keys_b)
    ]
    changed_items = []
    for k in (keys_a & keys_b):
        a, b = items_a[k], items_b[k]
        changes = {}
        if a.quantity != b.quantity:
            changes["quantity"] = {"from": a.quantity, "to": b.quantity}
        if a.unit_price != b.unit_price:
            changes["unit_price"] = {"from": a.unit_price, "to": b.unit_price}
        if a.discount_pct != b.discount_pct:
            changes["discount_pct"] = {"from": a.discount_pct, "to": b.discount_pct}
        if changes:
            changed_items.append({"key": k, "description": a.description, "changes": changes})

    summary_diff = {
        "subtotal": {"from": quote_a.subtotal, "to": quote_b.subtotal},
        "grand_total": {"from": quote_a.grand_total, "to": quote_b.grand_total},
        "currency": {"from": quote_a.currency, "to": quote_b.currency},
        "item_count": {"from": len(quote_a.items or []), "to": len(quote_b.items or [])},
    }

    return {
        "quote_a": quote_id,
        "quote_b": other_id,
        "added_items": added_items,
        "removed_items": removed_items,
        "changed_items": changed_items,
        "summary_diff": summary_diff,
    }


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
        "has_pdf": bool(quote.pdf_path),
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
