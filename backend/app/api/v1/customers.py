from __future__ import annotations

import io
import math

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import delete, func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.rate_limit import enforce_bulk_rate_limit
from app.models.customer import Customer
from app.models.quote import Quote
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.services.enrichment_service import EnrichmentService
from app.services.tenant_context import assert_same_tenant, scoped_for_user

router = APIRouter(prefix="/customers", tags=["Customers"])


# Round-10 R10-API-5 — `response_model=PaginatedResponse` documents the
# canonical {items, total, page, page_size, pages} envelope in the
# generated OpenAPI schema without forcing a full Pydantic model for
# every dict field. The items themselves remain `dict[str, Any]` so
# the existing serializers (which carry computed/joined fields like
# `pinned`, `stats`, `health_score`) work unchanged.
@router.get("/", response_model=PaginatedResponse[CustomerResponse])
async def list_customers(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, description="Search by name, company, or email"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List customers with pagination and search."""
    count_query = select(func.count(Customer.id))

    search_condition = None
    if search:
        safe_search = search.replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{safe_search}%"
        search_condition = or_(
            Customer.name.ilike(search_term),
            Customer.company.ilike(search_term),
            Customer.email.ilike(search_term),
        )
        count_query = count_query.where(search_condition)

    # V12 multi-tenant — apply before counting; no-op when
    # current_user.tenant_id is None.
    count_query = scoped_for_user(count_query, current_user, column=Customer.tenant_id)

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

    main_query = scoped_for_user(main_query, current_user, column=Customer.tenant_id)

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


@router.get("/high-intent", response_model=PaginatedResponse[dict])
async def list_high_intent_accounts(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sprint 4 — rule-based high-intent customers (+ pinned first)."""
    from app.services.prospecting_agent import ProspectingAgent

    rows = await ProspectingAgent(db).list_high_intent_accounts(current_user, limit=limit)
    items = [
        {
            "customer_id": r.customer_id,
            "name": r.name,
            "company": r.company,
            "score": r.score,
            "signals": r.signals,
            "pinned": r.pinned,
        }
        for r in rows
    ]
    total = len(rows)
    # Aligned with the canonical pagination envelope
    # ({items,total,page,page_size,pages}) used by list_customers so
    # frontend list components don't need to special-case this endpoint.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": limit,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/{customer_id}/pin", status_code=201)
async def pin_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user_customer_pin import UserCustomerPin

    cust = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not cust:
        raise NotFoundException("Musteri bulunamadi")

    existing = (
        await db.execute(
            select(UserCustomerPin).where(
                UserCustomerPin.user_id == current_user.id,
                UserCustomerPin.customer_id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        # Round-15 Sprint 15o cohort 5 — user_customer_pins.tenant_id NOT NULL.
        db.add(
            UserCustomerPin(
                user_id=current_user.id,
                customer_id=customer_id,
                tenant_id=current_user.tenant_id,
            )
        )
        await db.flush()
    return {"pinned": True, "customer_id": customer_id}


@router.delete("/{customer_id}/pin", status_code=200)
async def unpin_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user_customer_pin import UserCustomerPin

    await db.execute(
        delete(UserCustomerPin).where(
            UserCustomerPin.user_id == current_user.id,
            UserCustomerPin.customer_id == customer_id,
        )
    )
    await db.flush()
    return {"pinned": False, "customer_id": customer_id}


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get customer detail with quote statistics.

    Round-13 Sprint 6a — wires ``response_model=CustomerResponse`` so
    detail GET shows up in OpenAPI with the same shape as the list
    endpoint. ``CustomerResponse`` is extras-tolerant (R10-API-6), so
    the caller-specific ``pinned`` / ``stats`` extras still round-trip.
    """
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

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

    from app.models.user_customer_pin import UserCustomerPin

    pin_row = (
        await db.execute(
            select(UserCustomerPin).where(
                UserCustomerPin.user_id == current_user.id,
                UserCustomerPin.customer_id == customer_id,
            )
        )
    ).scalar_one_or_none()

    data = _customer_to_dict(customer)
    data["pinned"] = pin_row is not None
    data["stats"] = {
        "total_quotes": quote_count,
        "total_value": round(total_value, 2),
        "sent_quotes": sent_count,
    }
    return data


@router.get("/{customer_id}/intelligence")
async def get_customer_intelligence(
    customer_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified Customer/Account intelligence payload (v2).

    Returns operational context without triggering any LLM calls:
    - active opportunities for the customer
    - open task count across those opportunities
    - recent opportunity signals across those opportunities
    """
    customer = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    # Round-10 R10-API-3 — assert tenant before exposing any customer
    # intelligence. Without this, a cross-tenant probe of a known id
    # returned 200 with the user's own (empty) opportunity rows,
    # confirming the foreign-tenant customer existed.
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    from app.models.activity_log import ActivityLog
    from app.models.opportunity import Opportunity, OpportunitySignal, Task

    opp_conds = [Opportunity.customer_id == customer_id, Opportunity.status == "active"]
    if current_user.role == UserRole.SALES_REP.value:
        opp_conds.append(Opportunity.owner_id == current_user.id)

    opps = (
        await db.execute(
            select(Opportunity)
            .where(and_(*opp_conds))
            .order_by(Opportunity.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    opp_ids = [int(o.id) for o in opps]

    open_tasks_count = 0
    if opp_ids:
        open_tasks_count = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.opportunity_id.in_(opp_ids),
                    Task.status == "open",
                )
            )
        ).scalar() or 0

    last_activity_map: dict[int, datetime | None] = {}
    if opp_ids:
        last_rows = (
            await db.execute(
                select(ActivityLog.opportunity_id, func.max(ActivityLog.created_at))
                .where(ActivityLog.opportunity_id.in_(opp_ids))
                .group_by(ActivityLog.opportunity_id)
            )
        ).all()
        last_activity_map = {int(row[0]): row[1] for row in last_rows}

    signals = []
    if opp_ids:
        signals = (
            await db.execute(
                select(OpportunitySignal)
                .where(OpportunitySignal.opportunity_id.in_(opp_ids))
                .order_by(
                    OpportunitySignal.is_resolved.asc(),
                    OpportunitySignal.created_at.desc(),
                )
                .limit(50)
            )
        ).scalars().all()

    return {
        "customer": _customer_to_dict(customer),
        "opportunities": [
            {
                "id": o.id,
                "title": o.title,
                "stage": o.stage,
                "amount": o.amount,
                "currency": o.currency,
                "owner_id": o.owner_id,
                "close_date": str(o.close_date) if o.close_date else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
                "last_activity_at": (
                    last_activity_map.get(int(o.id)).isoformat()
                    if last_activity_map.get(int(o.id)) is not None
                    else None
                ),
            }
            for o in opps
        ],
        "open_tasks_count": int(open_tasks_count),
        "signals": [
            {
                "id": s.id,
                "opportunity_id": s.opportunity_id,
                "signal_type": s.signal_type,
                "severity": s.severity,
                "evidence": s.evidence,
                "source_type": s.source_type,
                "source_id": s.source_id,
                "is_resolved": s.is_resolved,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ],
    }


@router.get("/{customer_id}/account-360")
async def get_account_360(
    customer_id: int,
    refresh: bool = Query(False, description="Zorunlu rollup yenileme"),
    timeline_limit: int = Query(40, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sprint 3 — Account360: rollup + coklu firsat zaman cizelgesi + acik deal + risk + son temas."""
    from app.services.account_aggregate_service import AccountAggregateService

    customer = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    # Round-10 R10-API-3 — see get_customer_intelligence for rationale.
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    svc = AccountAggregateService(db)
    row = await svc.ensure_fresh(customer_id, current_user, refresh=refresh)
    extra = row.extra if isinstance(row.extra, dict) else {}

    enrichment = {
        "customer_id": customer_id,
        "pipeline_open_amount": round(float(row.pipeline_open_amount), 2),
        "closed_won_revenue": round(float(row.closed_won_revenue), 2),
        "active_deal_count": int(row.active_deal_count),
        "won_deal_count": int(row.won_deal_count),
        "lost_deal_count": int(row.lost_deal_count),
        "total_deal_count": int(row.total_deal_count),
        "risk_index": round(float(row.risk_index), 1),
        "engagement_score": round(float(row.engagement_score), 1),
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "health_score": extra.get("health_score"),
        "health_risk_level": extra.get("health_risk_level"),
    }

    last_touch = {
        "at": row.last_touch_at.isoformat() if row.last_touch_at else None,
        "source": extra.get("last_touch_source") or "unknown",
        "summary": extra.get("last_touch_summary") or "",
    }

    timeline = await svc.merge_multi_opportunity_timeline(
        customer_id, current_user, limit=timeline_limit
    )
    open_deals = await svc.open_deals(customer_id, current_user)
    risk_summary = await svc.risk_summary(customer_id, current_user)

    ccy = (extra.get("display_currency") if extra else None) or (
        open_deals[0].get("currency") if open_deals else None
    )
    enrichment["currency"] = (str(ccy).strip() if ccy else "") or "TRY"

    return {
        "customer_id": customer_id,
        "enrichment": enrichment,
        "last_touch": last_touch,
        "open_deals": open_deals,
        "risk_summary": risk_summary,
        "timeline": timeline,
    }


@router.post("/", status_code=201, response_model=CustomerResponse)
async def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customer.

    Round-13 Sprint 6a — response_model added so the 201 surface is
    typed in OpenAPI; CustomerResponse is extras-tolerant.
    """
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
        # R5-FORM-3 — thread enrichment fields the SPA submits but
        # which were silently dropped by the prior schema.
        website=data.website,
        linkedin_url=data.linkedin_url,
        industry=data.industry,
        employee_count=data.employee_count,
        annual_revenue=data.annual_revenue,
        parent_id=data.parent_id,
        territory_id=data.territory_id,
        created_by=current_user.id,
        # V12 multi-tenant: inherit caller's tenant.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)

    # Round-4 R4-EVT-201 — webhook subscribers configured for
    # ``customer.created`` were never firing because no producer
    # existed. Emit on the canonical create path so external
    # integrations (HubSpot sync, Slack notifier, etc.) can react.
    try:
        from app.core.event_bus import event_bus

        await event_bus.publish(
            "customer.created",
            {
                "customer_id": customer.id,
                "name": customer.name,
                "owner_id": customer.created_by,
                "tenant_id": customer.tenant_id,
            },
        )
    except Exception:
        # Best-effort — never let a downstream subscriber failure
        # break the user-visible create response.
        pass

    return _customer_to_dict(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
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
        raise NotFoundException("Musteri bulunamadi")
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    updates = data.model_dump(exclude_unset=True)

    # Check email uniqueness if email is being changed
    if "email" in updates and updates["email"] != customer.email:
        dup = await db.execute(
            select(Customer).where(Customer.email == updates["email"], Customer.id != customer_id)
        )
        if dup.scalar_one_or_none():
            raise BadRequestException(f"'{updates['email']}' e-posta adresine sahip baska musteri mevcut")

    for field, value in updates.items():
        setattr(customer, field, value)

    await db.flush()
    await db.refresh(customer)

    return _customer_to_dict(customer)


@router.post("/{customer_id}/enrich")
async def enrich_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enrich customer data using Claude AI."""
    service = EnrichmentService(db)
    try:
        result = await service.enrich_customer(customer_id)
    except ValueError as exc:
        raise NotFoundException(str(exc))
    return {"data": result}


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
        raise NotFoundException("Musteri bulunamadi")
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

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

    from app.core.upload_utils import read_upload_file_limited
    content = await read_upload_file_limited(file, max_bytes=5 * 1024 * 1024)

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
                # Round-15 Sprint 15k cohort 1 — Customer.tenant_id
                # NOT NULL. Inherit caller's tenant.
                tenant_id=getattr(current_user, "tenant_id", None),
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
        "message": "Icerik aktarimi tamamlandi",
        "imported": imported_count,
        "skipped": skipped_count,
        "errors": errors,
    }


@router.get("/{customer_id}/timeline")
async def get_customer_timeline(
    customer_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Feature-10: Customer 360 timeline — chronological emails + quotes."""
    from app.models.email_request import EmailRequest

    # Verify customer exists + tenant scope.
    # Round-10 R10-API-3 — promoted existence check to a tenant check so
    # cross-tenant id probes return 404 instead of an empty timeline.
    cust_row = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if not cust_row:
        raise NotFoundException(f"Musteri bulunamadi: {customer_id}")
    assert_same_tenant(cust_row, current_user, exception_cls=NotFoundException)

    events = []

    # Emails
    emails_q = await db.execute(
        select(EmailRequest.id, EmailRequest.subject, EmailRequest.from_address,
               EmailRequest.status, EmailRequest.created_at)
        .where(EmailRequest.customer_id == customer_id)
        .order_by(EmailRequest.created_at.desc())
        .limit(limit)
    )
    for e in emails_q.all():
        events.append({
            "type": "email",
            "id": e.id,
            "title": e.subject or "(Konu yok)",
            "detail": e.from_address,
            "status": e.status,
            "timestamp": e.created_at.isoformat() if e.created_at else None,
        })

    # Quotes
    quotes_q = await db.execute(
        select(Quote.id, Quote.quote_number, Quote.status, Quote.grand_total,
               Quote.currency, Quote.created_at)
        .where(Quote.customer_id == customer_id)
        .order_by(Quote.created_at.desc())
        .limit(limit)
    )
    for q in quotes_q.all():
        events.append({
            "type": "quote",
            "id": q.id,
            "title": q.quote_number,
            "detail": f"{q.grand_total:,.2f} {q.currency}",
            "status": q.status,
            "timestamp": q.created_at.isoformat() if q.created_at else None,
        })

    # Sort chronologically descending
    events.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    return {"customer_id": customer_id, "events": events[:limit]}


@router.get("/{customer_id}/activity-timeline")
async def get_customer_activity_timeline(
    customer_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified activity timeline — auto-captured events from all entity types."""
    from app.models.activity_log import ActivityLog
    from sqlalchemy.orm import defer

    # Verify customer exists + tenant scope. R10-API-3.
    cust_row = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if not cust_row:
        raise NotFoundException("Musteri bulunamadi")
    assert_same_tenant(cust_row, current_user, exception_cls=NotFoundException)

    # `source_ref` is excluded from the SELECT list — see the activity
    # feed endpoint (api/v1/activities.py) for the rationale; same
    # schema-drift guard applies here.
    result = await db.execute(
        select(ActivityLog)
        .options(defer(ActivityLog.source_ref))
        .where(ActivityLog.customer_id == customer_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    activities = result.scalars().all()

    return {
        "customer_id": customer_id,
        "activities": [
            {
                "id": a.id,
                "activity_type": a.activity_type,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "summary": a.summary,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],
    }


@router.post(
    "/bulk-action",
    # Round-4 R4-RL-2 — DoS + audit-log flood guard.
    dependencies=[Depends(enforce_bulk_rate_limit)],
)
async def bulk_action_customers(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk actions on customers: delete, assign, export."""
    ids = body.get("ids", [])
    action = body.get("action", "")
    params = body.get("params", {})

    if not ids or not isinstance(ids, list):
        raise BadRequestException("Gecerli bir ID listesi saglanmalidir")
    if not action:
        raise BadRequestException("Islem tipi belirtilmelidir")

    # Validate that all IDs exist AND belong to the caller's tenant.
    # Without this guard a sales rep could mutate or export any
    # tenant's customers by guessing IDs (audit TEN-4, 2026-05-01).
    # Mirrors the round-2 TEN-1 fix on opportunities.bulk-action.
    result = await db.execute(
        scoped_for_user(
            select(Customer), current_user, column=Customer.tenant_id,
        ).where(Customer.id.in_(ids))
    )
    customers = result.scalars().all()
    found_ids = {c.id for c in customers}
    missing_ids = [i for i in ids if i not in found_ids]
    if missing_ids:
        raise NotFoundException(f"Bulunamayan musteri ID'leri: {missing_ids}")

    if action == "delete":
        # Manager only
        if current_user.role != UserRole.SALES_MANAGER.value:
            raise BadRequestException("Silme islemi yalnizca yonetici tarafindan yapilabilir")
        from app.services.activity_logger import log_activity
        affected_count = 0
        for customer in customers:
            quote_count = await db.execute(
                select(func.count(Quote.id)).where(Quote.customer_id == customer.id)
            )
            if (quote_count.scalar() or 0) > 0:
                continue
            from app.models.email_request import EmailRequest
            await db.execute(
                EmailRequest.__table__.update()
                .where(EmailRequest.customer_id == customer.id)
                .values(customer_id=None)
            )
            # KVKK / SOX-style audit trail for destructive bulk actions
            # (audit AUD-2). Logged before delete so the entity_id is
            # still resolvable.
            await log_activity(
                db,
                activity_type="customer_deleted_bulk",
                entity_type="customer",
                entity_id=customer.id,
                customer_id=customer.id,
                user_id=current_user.id,
                summary=f"Toplu silme: {customer.name or customer.company or '#' + str(customer.id)}",
                source_ref=f"bulk_action:{customer.id}",
            )
            await db.delete(customer)
            affected_count += 1
        await db.flush()
        return {"message": f"{affected_count} musteri silindi", "affected_count": affected_count}

    if action == "assign":
        new_owner_id = params.get("created_by")
        if not new_owner_id:
            raise BadRequestException("Atanacak kullanici ID'si (created_by) belirtilmelidir")
        for customer in customers:
            customer.created_by = new_owner_id
        await db.flush()
        return {"message": f"{len(customers)} musteri atandi", "affected_count": len(customers)}

    if action == "export":
        rows = []
        for customer in customers:
            rows.append(_customer_to_dict(customer))
        return {"message": f"{len(rows)} musteri disa aktarildi", "affected_count": len(rows), "data": rows}

    raise BadRequestException(f"Bilinmeyen islem: {action}")


@router.get("/{customer_id}/hierarchy")
async def get_customer_hierarchy(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the customer's parent chain and subsidiaries tree."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Round-10 R10-API-3 — tenant gate. The parent-chain walk and the
    # subsidiaries query both used to follow FKs across tenant
    # boundaries, leaking the existence (and name/company) of foreign-
    # tenant customers if a user planted a cross-tenant parent_id.
    assert_same_tenant(customer, user, exception_cls=NotFoundException)

    # Get parent chain — same-tenant only.
    parents = []
    current = customer
    depth = 0
    while current.parent_id and depth < 5:
        p_result = await db.execute(
            select(Customer).where(
                Customer.id == current.parent_id,
                Customer.tenant_id == customer.tenant_id,
            )
        )
        parent = p_result.scalar_one_or_none()
        if not parent:
            break
        parents.append({"id": parent.id, "name": parent.name, "company": parent.company})
        current = parent
        depth += 1

    # Get direct subsidiaries — same-tenant only.
    subs_result = await db.execute(
        select(Customer).where(
            Customer.parent_id == customer_id,
            Customer.tenant_id == customer.tenant_id,
        )
    )
    subsidiaries = subs_result.scalars().all()

    return {
        "customer_id": customer_id,
        "parents": list(reversed(parents)),
        "subsidiaries": [
            {"id": s.id, "name": s.name, "company": s.company}
            for s in subsidiaries
        ],
    }


@router.patch("/{customer_id}/parent")
async def set_customer_parent(
    customer_id: int,
    parent_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set or unset parent customer. Validates no circular references."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Round-10 R10-API-3 — gate child and parent on the same tenant so
    # an attacker can't reparent their own customer onto another
    # tenant's customer to discover its existence.
    assert_same_tenant(customer, user, exception_cls=NotFoundException)

    if parent_id is not None:
        if parent_id == customer_id:
            raise HTTPException(status_code=400, detail="Cannot be parent of self")

        # Check parent exists in the SAME tenant.
        p_result = await db.execute(
            select(Customer).where(
                Customer.id == parent_id,
                Customer.tenant_id == customer.tenant_id,
            )
        )
        if not p_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent customer not found")

        # Check for circular reference (same-tenant chain only).
        current_id = parent_id
        depth = 0
        while current_id and depth < 10:
            if current_id == customer_id:
                raise HTTPException(status_code=400, detail="Circular reference detected")
            r = await db.execute(
                select(Customer.parent_id).where(
                    Customer.id == current_id,
                    Customer.tenant_id == customer.tenant_id,
                )
            )
            row = r.scalar_one_or_none()
            current_id = row
            depth += 1

    customer.parent_id = parent_id
    await db.commit()
    return {"status": "ok", "parent_id": parent_id}


@router.get("/{customer_id}/rollup")
async def get_customer_rollup(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Aggregate metrics across all subsidiary customers."""
    from app.models.opportunity import Opportunity
    from app.models.quote import Quote

    # Collect all descendant IDs (BFS, depth limit 5)
    all_ids = [customer_id]
    queue = [customer_id]
    depth = 0
    while queue and depth < 5:
        r = await db.execute(
            select(Customer.id).where(Customer.parent_id.in_(queue))
        )
        children = [row for row in r.scalars().all()]
        if not children:
            break
        all_ids.extend(children)
        queue = children
        depth += 1

    # Count opportunities
    opp_result = await db.execute(
        select(func.count(), func.coalesce(func.sum(Opportunity.amount), 0))
        .where(Opportunity.customer_id.in_(all_ids))
    )
    opp_count, opp_total = opp_result.one()

    # Count quotes
    quote_result = await db.execute(
        select(func.count(), func.coalesce(func.sum(Quote.grand_total), 0))
        .where(Quote.customer_id.in_(all_ids))
    )
    quote_count, quote_total = quote_result.one()

    return {
        "customer_id": customer_id,
        "subsidiary_count": len(all_ids) - 1,
        "total_opportunities": opp_count,
        "total_opportunity_value": float(opp_total),
        "total_quotes": quote_count,
        "total_quote_value": float(quote_total),
    }


def _customer_to_dict(customer: Customer) -> dict:
    """Convert Customer to a dictionary response.

    Note on KVKK fields: ``kvkk_consent`` / ``kvkk_consent_date`` /
    ``kvkk_consent_method`` are intentionally NOT projected here.
    They are PII-grade and surface only via the dedicated KVKK
    admin endpoint so that audit logging and access controls can be
    applied at that boundary.

    Field-level masking (R4-PERM-1) is applied via
    ``apply_request_perms`` using the request-scoped permission CV
    populated by ``get_current_user``.
    """
    from app.services.field_permission_service import apply_request_perms

    data = {
        "id": customer.id,
        # Round-trip tenant_id so the frontend can verify isolation
        # and analytics layers can group correctly (audit CU-3).
        "tenant_id": customer.tenant_id,
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
        "industry": customer.industry,
        "employee_count": customer.employee_count,
        "annual_revenue": customer.annual_revenue,
        "website": customer.website,
        "linkedin_url": customer.linkedin_url,
        "enriched_at": customer.enriched_at.isoformat() if customer.enriched_at else None,
        # Account hierarchy + segmentation. Useful for territory
        # filters and parent/child breadcrumbs once those UIs land;
        # exposing now so the API contract is consistent.
        "parent_id": getattr(customer, "parent_id", None),
        "territory_id": getattr(customer, "territory_id", None),
        # R5-API metadata — surface compliance state so the SPA can
        # render a "pending deletion" banner / data classification
        # badge without re-querying. KVKK consent itself is still
        # gated behind /compliance/* (handled in _customer_to_dict's
        # docstring above).
        "data_classification": getattr(customer, "data_classification", None),
        "deletion_requested_at": (
            customer.deletion_requested_at.isoformat()
            if getattr(customer, "deletion_requested_at", None)
            else None
        ),
    }
    return apply_request_perms(data, "customer")
