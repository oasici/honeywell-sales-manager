"""KVKK / data privacy compliance endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.rate_limit import enforce_kvkk_export_rate_limit
from app.models.activity_log import ActivityLog
from app.models.audit_log import AuditLog
from app.models.breach_notification import BreachNotification
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.retention_policy import RetentionPolicy
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user

logger = logging.getLogger(__name__)


def _require_compliance() -> None:
    """Round-4 R4-FLAG-3 — gate the entire KVKK module on a feature flag.

    Pre-fix, a tenant on a plan that didn't include the KVKK module
    could still call /compliance/data-export and exfiltrate full PII.
    The closest existing flag is ``FEATURE_BREACH_WORKFLOW`` which
    governs the breach-workflow surface; reusing it here ensures the
    module turns on/off as a unit.
    """
    if not settings.FEATURE_BREACH_WORKFLOW:
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(
    prefix="/compliance",
    tags=["KVKK Compliance"],
    dependencies=[Depends(_require_compliance)],
)

DEFAULT_RETENTION_YEARS = 3
VALID_CONSENT_METHODS = {"email", "form", "verbal", "import"}
VALID_RETENTION_ACTIONS = {"anonymize", "archive", "notify"}
VALID_RETENTION_ENTITIES = {"customer", "email", "quote", "activity_log"}
VALID_BREACH_STATUSES = {"open", "investigating", "notified", "closed"}


class ConsentRequest(BaseModel):
    consent: bool
    method: str = Field(..., max_length=50)
    purpose: str = Field(..., max_length=200)


class RetentionPolicyCreate(BaseModel):
    entity_type: str = Field(..., max_length=30)
    retention_days: int = Field(..., ge=1)
    action: str = Field(default="notify", max_length=20)
    is_active: bool = True


class RetentionPolicyUpdate(BaseModel):
    retention_days: int | None = Field(default=None, ge=1)
    action: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class BreachCreate(BaseModel):
    breach_type: str = Field(..., max_length=50)
    description: str | None = None
    affected_customers_json: str | None = None
    severity: str = Field(default="high", max_length=20)


class BreachUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=20)
    description: str | None = None
    severity: str | None = Field(default=None, max_length=20)


@router.post("/consent/{customer_id}")
async def record_consent(
    customer_id: int,
    body: ConsentRequest,
    current_user: User = Depends(
        require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Record KVKK consent for a customer."""
    if body.method not in VALID_CONSENT_METHODS:
        raise BadRequestException(
            f"Gecersiz onay yontemi: {body.method}. "
            f"Gecerli yontemler: {', '.join(sorted(VALID_CONSENT_METHODS))}"
        )

    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    # Cross-tenant access maps to 404 — KVKK endpoints must not leak
    # cross-tenant existence and must not allow destructive ops on
    # foreign-tenant customers.
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    now = datetime.now(timezone.utc)
    customer.kvkk_consent = body.consent
    customer.kvkk_consent_date = now
    customer.kvkk_consent_method = body.method
    customer.data_processing_purpose = body.purpose
    customer.data_retention_until = now + timedelta(days=DEFAULT_RETENTION_YEARS * 365)

    # Audit log entry
    audit = AuditLog(
        user_id=current_user.id,
        action="kvkk_consent",
        entity_type="customer",
        entity_id=customer_id,
        changes=json.dumps({
            "consent": body.consent,
            "method": body.method,
            "purpose": body.purpose,
        }),
    )
    db.add(audit)
    await db.flush()

    return {
        "message": "KVKK onay bilgisi kaydedildi",
        "customer_id": customer_id,
        "has_consent": customer.kvkk_consent,
        "consent_date": customer.kvkk_consent_date.isoformat(),
        "method": customer.kvkk_consent_method,
        "purpose": customer.data_processing_purpose,
        "retention_until": customer.data_retention_until.isoformat(),
    }


@router.get("/consent/{customer_id}")
async def get_consent(
    customer_id: int,
    current_user: User = Depends(
        require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Return KVKK consent status for a customer."""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    # Cross-tenant access maps to 404 — KVKK endpoints must not leak
    # cross-tenant existence and must not allow destructive ops on
    # foreign-tenant customers.
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    return {
        "customer_id": customer.id,
        "has_consent": customer.kvkk_consent,
        "consent_date": (
            customer.kvkk_consent_date.isoformat()
            if customer.kvkk_consent_date
            else None
        ),
        "method": customer.kvkk_consent_method,
        "purpose": customer.data_processing_purpose,
        "retention_until": (
            customer.data_retention_until.isoformat()
            if customer.data_retention_until
            else None
        ),
    }


@router.post(
    "/data-export/{customer_id}",
    # Round-4 R4-RL-4 — without this, a SALES_MANAGER (or compromised
    # account) iterates customer_id={1..N} and exfiltrates the entire
    # KVKK PII corpus in minutes.
    dependencies=[Depends(enforce_kvkk_export_rate_limit)],
)
async def export_customer_data(
    customer_id: int,
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Export ALL customer data as JSON (KVKK data portability)."""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    # Cross-tenant access maps to 404 — KVKK endpoints must not leak
    # cross-tenant existence and must not allow destructive ops on
    # foreign-tenant customers.
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    # Customer fields
    customer_data = {
        "id": customer.id,
        "name": customer.name,
        "company": customer.company,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "tax_id": customer.tax_id,
        "preferred_lang": customer.preferred_lang,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
        "kvkk_consent": customer.kvkk_consent,
        "kvkk_consent_date": (
            customer.kvkk_consent_date.isoformat()
            if customer.kvkk_consent_date
            else None
        ),
        "kvkk_consent_method": customer.kvkk_consent_method,
        "data_processing_purpose": customer.data_processing_purpose,
    }

    # Quotes
    quotes_result = await db.execute(
        select(Quote).where(Quote.customer_id == customer_id)
    )
    quotes = [
        {
            "id": q.id,
            "quote_number": q.quote_number,
            "status": q.status,
            "currency": q.currency,
            "grand_total": q.grand_total if hasattr(q, "grand_total") else None,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        for q in quotes_result.scalars().all()
    ]

    # Emails
    emails_result = await db.execute(
        select(EmailRequest).where(EmailRequest.customer_id == customer_id)
    )
    emails = [
        {
            "id": e.id,
            "subject": e.subject,
            "from_address": e.from_address,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in emails_result.scalars().all()
    ]

    # Opportunities
    opps_result = await db.execute(
        select(Opportunity).where(Opportunity.customer_id == customer_id)
    )
    opportunities = [
        {
            "id": o.id,
            "title": o.title,
            "stage": o.stage,
            "amount": o.amount,
            "currency": o.currency,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in opps_result.scalars().all()
    ]

    # Activity logs — `source_ref` is excluded from the SELECT list to
    # survive partial schema-drift; this serializer doesn't read it.
    activities_result = await db.execute(
        select(ActivityLog)
        .options(defer(ActivityLog.source_ref))
        .where(ActivityLog.customer_id == customer_id)
    )
    activities = [
        {
            "id": a.id,
            "activity_type": a.activity_type,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "summary": a.summary,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in activities_result.scalars().all()
    ]

    # Audit log for this export
    audit = AuditLog(
        user_id=current_user.id,
        action="kvkk_data_export",
        entity_type="customer",
        entity_id=customer_id,
        changes=json.dumps({"exported_by": current_user.id}),
    )
    db.add(audit)
    await db.flush()

    return {
        "customer": customer_data,
        "quotes": quotes,
        "emails": emails,
        "opportunities": opportunities,
        "activities": activities,
    }


@router.post("/data-delete/{customer_id}")
async def anonymize_customer_data(
    customer_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Anonymize customer data (KVKK right to erasure). Preserves row for referential integrity."""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    # Cross-tenant access maps to 404 — KVKK endpoints must not leak
    # cross-tenant existence and must not allow destructive ops on
    # foreign-tenant customers.
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    if customer.deletion_requested_at is not None:
        raise BadRequestException("Bu musteri zaten anonimlestirilmis")

    now = datetime.now(timezone.utc)

    # Anonymize PII fields
    customer.name = "ANONIMLESTIRILDI"
    customer.email = f"anon_{customer_id}@deleted.local"
    customer.phone = None
    customer.address = None
    customer.tax_id = None
    customer.company = None
    customer.deletion_requested_at = now
    customer.kvkk_consent = False

    # Audit log entry
    audit = AuditLog(
        user_id=current_user.id,
        action="kvkk_data_delete",
        entity_type="customer",
        entity_id=customer_id,
        changes=json.dumps({
            "anonymized_at": now.isoformat(),
            "anonymized_by": current_user.id,
        }),
    )
    db.add(audit)
    await db.flush()

    logger.info(
        "Customer %d anonymized by user %d (KVKK)",
        customer_id,
        current_user.id,
    )

    return {
        "message": "Musteri verileri anonimlestirildi",
        "customer_id": customer_id,
    }


@router.get("/retention-report")
async def retention_report(
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List customers whose data retention period has expired but not yet anonymized."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        scoped_for_user(
            select(Customer), current_user, column=Customer.tenant_id
        ).where(
            Customer.data_retention_until < now,
            Customer.deletion_requested_at.is_(None),
        )
    )
    customers = result.scalars().all()

    return {
        "overdue_count": len(customers),
        "customers": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "retention_until": (
                    c.data_retention_until.isoformat()
                    if c.data_retention_until
                    else None
                ),
                "kvkk_consent": c.kvkk_consent,
            }
            for c in customers
        ],
    }


@router.get("/audit-trail/{customer_id}")
async def customer_audit_trail(
    customer_id: int,
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Return all audit log entries related to a customer."""
    # Verify customer exists in this tenant.
    cust_result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise NotFoundException("Musteri bulunamadi")
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "customer",
            AuditLog.entity_id == customer_id,
        )
        .order_by(AuditLog.created_at.desc())
    )
    entries = result.scalars().all()

    return {
        "customer_id": customer_id,
        "audit_entries": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "changes": e.changes,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }


# ══════════════════════════════════════════
# RETENTION POLICIES
# ══════════════════════════════════════════


@router.get("/retention-policies")
async def list_retention_policies(
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List all data retention policies."""
    result = await db.execute(
        select(RetentionPolicy).order_by(RetentionPolicy.entity_type)
    )
    policies = result.scalars().all()

    return {
        "policies": [
            {
                "id": p.id,
                "entity_type": p.entity_type,
                "retention_days": p.retention_days,
                "action": p.action,
                "is_active": p.is_active,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in policies
        ],
    }


@router.post("/retention-policies", status_code=201)
async def create_retention_policy(
    body: RetentionPolicyCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a data retention policy."""
    if body.entity_type not in VALID_RETENTION_ENTITIES:
        raise BadRequestException(
            f"Gecersiz varlik tipi: {body.entity_type}. "
            f"Gecerli tipler: {', '.join(sorted(VALID_RETENTION_ENTITIES))}"
        )
    if body.action not in VALID_RETENTION_ACTIONS:
        raise BadRequestException(
            f"Gecersiz aksiyon: {body.action}. "
            f"Gecerli aksiyonlar: {', '.join(sorted(VALID_RETENTION_ACTIONS))}"
        )

    policy = RetentionPolicy(
        entity_type=body.entity_type,
        retention_days=body.retention_days,
        action=body.action,
        is_active=body.is_active,
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)

    return {
        "id": policy.id,
        "entity_type": policy.entity_type,
        "retention_days": policy.retention_days,
        "action": policy.action,
        "is_active": policy.is_active,
    }


@router.put("/retention-policies/{policy_id}")
async def update_retention_policy(
    policy_id: int,
    body: RetentionPolicyUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a data retention policy."""
    result = await db.execute(
        select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise NotFoundException("Saklama politikasi bulunamadi")

    update_data = body.model_dump(exclude_unset=True)
    if "action" in update_data and update_data["action"] not in VALID_RETENTION_ACTIONS:
        raise BadRequestException(
            f"Gecersiz aksiyon: {update_data['action']}. "
            f"Gecerli aksiyonlar: {', '.join(sorted(VALID_RETENTION_ACTIONS))}"
        )

    for key, value in update_data.items():
        setattr(policy, key, value)

    await db.flush()

    return {
        "id": policy.id,
        "entity_type": policy.entity_type,
        "retention_days": policy.retention_days,
        "action": policy.action,
        "is_active": policy.is_active,
    }


@router.delete("/retention-policies/{policy_id}", status_code=204)
async def delete_retention_policy(
    policy_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a data retention policy."""
    result = await db.execute(
        select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise NotFoundException("Saklama politikasi bulunamadi")

    await db.delete(policy)


# ══════════════════════════════════════════
# BREACH NOTIFICATIONS
# ══════════════════════════════════════════


@router.post("/breach", status_code=201)
async def create_breach_notification(
    body: BreachCreate,
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Create a breach notification record."""
    breach = BreachNotification(
        breach_type=body.breach_type,
        description=body.description,
        affected_customers_json=body.affected_customers_json,
        severity=body.severity,
        created_by=current_user.id,
    )
    db.add(breach)
    await db.flush()
    await db.refresh(breach)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="breach_created",
        entity_type="breach_notification",
        entity_id=breach.id,
        changes=json.dumps({
            "breach_type": body.breach_type,
            "severity": body.severity,
        }),
    )
    db.add(audit)
    await db.flush()

    logger.warning(
        "Breach notification created: id=%d type=%s severity=%s by user=%d",
        breach.id,
        body.breach_type,
        body.severity,
        current_user.id,
    )

    return {
        "id": breach.id,
        "breach_type": breach.breach_type,
        "status": breach.status,
        "severity": breach.severity,
        "created_at": breach.created_at.isoformat() if breach.created_at else None,
    }


@router.patch("/breach/{breach_id}")
async def update_breach_notification(
    breach_id: int,
    body: BreachUpdate,
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Update breach notification status."""
    result = await db.execute(
        select(BreachNotification).where(BreachNotification.id == breach_id)
    )
    breach = result.scalar_one_or_none()
    if not breach:
        raise NotFoundException("Ihlal bildirimi bulunamadi")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in VALID_BREACH_STATUSES:
        raise BadRequestException(
            f"Gecersiz durum: {update_data['status']}. "
            f"Gecerli durumlar: {', '.join(sorted(VALID_BREACH_STATUSES))}"
        )

    # Track notification timestamp
    if update_data.get("status") == "notified" and not breach.notified_at:
        breach.notified_at = datetime.now(timezone.utc)

    for key, value in update_data.items():
        setattr(breach, key, value)

    await db.flush()

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="breach_updated",
        entity_type="breach_notification",
        entity_id=breach.id,
        changes=json.dumps(update_data),
    )
    db.add(audit)
    await db.flush()

    return {
        "id": breach.id,
        "breach_type": breach.breach_type,
        "status": breach.status,
        "severity": breach.severity,
        "notified_at": breach.notified_at.isoformat() if breach.notified_at else None,
    }


@router.get("/breaches")
async def list_breach_notifications(
    status: str | None = None,
    current_user: User = Depends(
        require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)
    ),
    db: AsyncSession = Depends(get_db),
):
    """List breach notifications."""
    query = select(BreachNotification).order_by(BreachNotification.created_at.desc())
    if status:
        if status not in VALID_BREACH_STATUSES:
            raise BadRequestException(f"Gecersiz durum filtresi: {status}")
        query = query.where(BreachNotification.status == status)

    result = await db.execute(query)
    breaches = result.scalars().all()

    return {
        "breaches": [
            {
                "id": b.id,
                "breach_type": b.breach_type,
                "description": b.description,
                "severity": b.severity,
                "status": b.status,
                "notified_at": b.notified_at.isoformat() if b.notified_at else None,
                "created_by": b.created_by,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in breaches
        ],
    }
