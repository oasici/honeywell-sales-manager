import io
import math

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.quote import Quote
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("/")
async def list_customers(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="Search by name, company, or email"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List customers with pagination and search."""
    count_query = select(func.count(Customer.id))

    search_condition = None
    if search:
        search_term = f"%{search}%"
        search_condition = or_(
            Customer.name.ilike(search_term),
            Customer.company.ilike(search_term),
            Customer.email.ilike(search_term),
        )
        count_query = count_query.where(search_condition)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Subquery for quote stats to avoid N+1
    quote_stats = (
        select(
            Quote.customer_id,
            func.count(Quote.id).label("qcount"),
            func.coalesce(func.sum(Quote.grand_total), 0.0).label("qvalue"),
        )
        .group_by(Quote.customer_id)
        .subquery()
    )

    main_query = (
        select(Customer, quote_stats.c.qcount, quote_stats.c.qvalue)
        .outerjoin(quote_stats, Customer.id == quote_stats.c.customer_id)
    )

    if search_condition is not None:
        main_query = main_query.where(search_condition)

    offset = (page - 1) * page_size
    main_query = main_query.order_by(Customer.name).offset(offset).limit(page_size)

    result = await db.execute(main_query)
    rows = result.all()

    items = []
    for customer, qcount, qvalue in rows:
        d = _customer_to_dict(customer)
        d["quote_count"] = qcount or 0
        d["total_quote_value"] = round(qvalue or 0.0, 2)
        items.append(d)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{customer_id}")
async def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get customer detail with quote statistics."""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException(f"{customer_id} numarali musteri bulunamadi")

    # Quote statistics
    quote_count_q = await db.execute(
        select(func.count(Quote.id)).where(Quote.customer_id == customer_id)
    )
    quote_count = quote_count_q.scalar() or 0

    total_value_q = await db.execute(
        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(
            Quote.customer_id == customer_id
        )
    )
    total_value = total_value_q.scalar() or 0.0

    sent_count_q = await db.execute(
        select(func.count(Quote.id)).where(
            and_(Quote.customer_id == customer_id, Quote.status == "sent")
        )
    )
    sent_count = sent_count_q.scalar() or 0

    data = _customer_to_dict(customer)
    data["stats"] = {
        "total_quotes": quote_count,
        "total_value": round(total_value, 2),
        "sent_quotes": sent_count,
    }
    return data


@router.post("/", status_code=201)
async def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customer."""
    # Check for duplicate email
    existing = await db.execute(
        select(Customer).where(Customer.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise BadRequestException(f"'{data.email}' e-posta adresine sahip musteri zaten mevcut")

    customer = Customer(
        name=data.name,
        email=data.email,
        company=data.company,
        phone=data.phone,
        address=data.address,
        tax_id=data.tax_id,
        preferred_lang=data.preferred_lang,
        created_by=current_user.id,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)

    return _customer_to_dict(customer)


@router.put("/{customer_id}")
async def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a customer."""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException(f"{customer_id} numarali musteri bulunamadi")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    await db.flush()
    await db.refresh(customer)

    return _customer_to_dict(customer)


@router.delete("/{customer_id}", status_code=200)
async def delete_customer(
    customer_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a customer. Only allowed if customer has no quotes."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException(f"{customer_id} numarali musteri bulunamadi")

    # Check for linked quotes
    quote_count = await db.execute(
        select(func.count(Quote.id)).where(Quote.customer_id == customer_id)
    )
    if (quote_count.scalar() or 0) > 0:
        raise BadRequestException("Teklifi olan musteri silinemez")

    # Unlink email_requests
    from app.models.email_request import EmailRequest
    await db.execute(
        EmailRequest.__table__.update()
        .where(EmailRequest.customer_id == customer_id)
        .values(customer_id=None)
    )

    await db.delete(customer)
    await db.flush()
    return {"message": f"Musteri {customer_id} silindi"}


@router.post("/import", status_code=201)
async def import_customers(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Import customers from Excel (.xlsx) or CSV file."""
    if not file.filename:
        raise BadRequestException("Dosya saglanmadi")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".csv") or filename_lower.endswith(".xlsx")):
        raise BadRequestException("Yalnizca .csv ve .xlsx dosyalari desteklenmektedir")

    content = await file.read()

    imported_count = 0
    skipped_count = 0
    errors = []

    try:
        if filename_lower.endswith(".csv"):
            import csv

            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        else:
            try:
                import openpyxl
            except ImportError:
                raise BadRequestException(
                    "openpyxl is required for Excel imports. Install it with: pip install openpyxl"
                )
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append(dict(zip(headers, row)))

        for i, row in enumerate(rows, start=2):
            name = str(row.get("name") or "").strip()
            email = str(row.get("email") or "").strip()

            if not name or not email:
                skipped_count += 1
                continue

            existing = await db.execute(
                select(Customer).where(Customer.email == email)
            )
            if existing.scalar_one_or_none():
                skipped_count += 1
                continue

            customer = Customer(
                name=name,
                email=email,
                company=str(row.get("company") or "").strip() or None,
                phone=str(row.get("phone") or "").strip() or None,
                address=str(row.get("address") or "").strip() or None,
                tax_id=str(row.get("tax_id") or "").strip() or None,
                preferred_lang=str(row.get("preferred_lang") or "tr").strip(),
                created_by=current_user.id,
            )
            db.add(customer)
            imported_count += 1

        await db.flush()

    except BadRequestException:
        raise
    except Exception as e:
        raise BadRequestException(f"Dosya isleme hatasi: {str(e)}")

    return {
        "message": "Import completed",
        "imported": imported_count,
        "skipped": skipped_count,
        "errors": errors,
    }


def _customer_to_dict(customer: Customer) -> dict:
    """Convert Customer to a dictionary response."""
    return {
        "id": customer.id,
        "name": customer.name,
        "company": customer.company,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "tax_id": customer.tax_id,
        "preferred_lang": customer.preferred_lang,
        "created_by": customer.created_by,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
        "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
    }
