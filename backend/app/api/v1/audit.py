"""Audit trail and KVKK data export endpoints (admin / compliance officer).

The list endpoint backs the admin audit trail UI (filterable, paginated).
The CSV export is for ad-hoc compliance reports. The data export is the
KVKK Article 15 right-of-access path: every record we hold about a given
user, returned as a single JSON document the operator can hand over.

All endpoints require sales_manager role.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["Audit"])

CSV_EXPORT_HARD_LIMIT = 10_000


@router.get("/")
async def list_audit_logs(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(None, description="Filter by user ID"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    entity_id: int | None = Query(None, description="Filter by entity ID"),
    action: str | None = Query(None, description="Filter by exact action"),
    action_prefix: str | None = Query(
        None, description="Filter by action prefix (e.g. 'kvkk_') — exclusive with action"
    ),
    since: datetime | None = Query(None, description="ISO 8601 — only events on/after this time"),
    until: datetime | None = Query(None, description="ISO 8601 — only events strictly before this time"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List audit logs with pagination and filters (sales_manager only)."""
    if action and action_prefix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action ve action_prefix birlikte kullanilamaz",
        )

    filters = _build_filters(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        action_prefix=action_prefix,
        since=since,
        until=until,
        # V13 — scope audit list to caller's tenant. None on
        # single-tenant deployments → unchanged behaviour.
        tenant_id=getattr(current_user, "tenant_id", None),
    )

    count_query = select(func.count(AuditLog.id))
    if filters:
        count_query = count_query.where(*filters)
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    main_query = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if filters:
        main_query = main_query.where(*filters)

    logs = (await db.execute(main_query)).scalars().all()

    return {
        "items": [_audit_log_to_dict(log) for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/export/csv")
async def export_audit_logs_csv(
    user_id: int | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    action: str | None = Query(None),
    action_prefix: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Export filtered audit logs as CSV (compliance reports).

    Capped at ``CSV_EXPORT_HARD_LIMIT`` rows so an unbounded query can't
    OOM the worker. Operators with larger windows should narrow the
    filter or run a DB-side export.
    """
    if action and action_prefix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action ve action_prefix birlikte kullanilamaz",
        )

    filters = _build_filters(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        action_prefix=action_prefix,
        since=since,
        until=until,
        tenant_id=getattr(current_user, "tenant_id", None),
    )

    query = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(CSV_EXPORT_HARD_LIMIT)
    )
    if filters:
        query = query.where(*filters)
    logs = (await db.execute(query)).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "user_id", "action", "entity_type", "entity_id", "ip_address", "created_at", "changes"])
    for log in logs:
        writer.writerow([
            log.id,
            log.user_id if log.user_id is not None else "",
            log.action,
            log.entity_type,
            log.entity_id,
            log.ip_address or "",
            log.created_at.isoformat() if log.created_at else "",
            log.changes or "",
        ])

    filename = f"audit-logs-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return PlainTextResponse(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/data-export/{target_user_id}")
async def export_user_data(
    target_user_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """KVKK Article 15 — return everything we hold about a single user.

    Bundles: the user record, audit events tied to them, customers they
    created, and opportunities they own. Output is a single JSON document
    the compliance officer can hand to the data subject.

    Writes its own audit row so the disclosure itself is logged.
    """
    user = (
        await db.execute(select(User).where(User.id == target_user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")

    audit_events = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == target_user_id)
            .order_by(AuditLog.created_at.desc())
        )
    ).scalars().all()

    created_customers = (
        await db.execute(select(Customer).where(Customer.created_by == target_user_id))
    ).scalars().all()

    owned_opportunities = (
        await db.execute(select(Opportunity).where(Opportunity.owner_id == target_user_id))
    ).scalars().all()

    # Email requests aren't directly owned by a user, but if the user's
    # email address matches a sender we surface those too.
    sent_emails = []
    if user.email:
        sent_emails = (
            await db.execute(
                select(EmailRequest).where(EmailRequest.from_address == user.email)
            )
        ).scalars().all()

    payload = {
        "exported_at": datetime.utcnow().isoformat(),
        "exported_by": current_user.id,
        "user": _user_to_dict(user),
        "audit_events": [_audit_log_to_dict(a) for a in audit_events],
        "created_customers": [_customer_to_dict(c) for c in created_customers],
        "owned_opportunities": [_opportunity_to_dict(o) for o in owned_opportunities],
        "sent_emails": [_email_request_to_dict(e) for e in sent_emails],
        "counts": {
            "audit_events": len(audit_events),
            "created_customers": len(created_customers),
            "owned_opportunities": len(owned_opportunities),
            "sent_emails": len(sent_emails),
        },
    }

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="kvkk_data_export",
            entity_type="user",
            entity_id=target_user_id,
            changes=json.dumps({
                "exported_at": payload["exported_at"],
                "counts": payload["counts"],
            }),
        )
    )
    await db.flush()

    return payload


# ─── helpers ─────────────────────────────────────────────────────────────


def _build_filters(
    *,
    user_id: int | None,
    entity_type: str | None,
    entity_id: int | None,
    action: str | None,
    action_prefix: str | None,
    since: datetime | None,
    until: datetime | None,
    tenant_id: int | None = None,
) -> list:
    """Build SQLAlchemy filter conditions from query parameters."""
    filters = []
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if entity_type is not None:
        filters.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        filters.append(AuditLog.entity_id == entity_id)
    if action is not None:
        filters.append(AuditLog.action == action)
    if action_prefix is not None:
        # Exact escaping isn't needed: action is a stable enum-like string,
        # but we still anchor with startswith semantics by appending a wildcard.
        filters.append(AuditLog.action.like(f"{action_prefix}%"))
    if since is not None:
        filters.append(AuditLog.created_at >= since)
    if until is not None:
        filters.append(AuditLog.created_at < until)
    # V13 multi-tenant scoping — applied transparently when the
    # caller has a tenant_id; legacy single-tenant audit views
    # (caller.tenant_id is None) see all rows like before.
    if tenant_id is not None:
        filters.append(AuditLog.tenant_id == tenant_id)
    return filters


def _audit_log_to_dict(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "tenant_id": log.tenant_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "changes": log.changes,
        "ip_address": log.ip_address,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _user_to_dict(user: User) -> dict:
    """Public-safe user fields for KVKK export. No password hash."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": getattr(user, "full_name", None),
        "role": getattr(user, "role", None),
        "is_active": getattr(user, "is_active", None),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    }


def _customer_to_dict(customer: Customer) -> dict:
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "company": customer.company,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
    }


def _opportunity_to_dict(opp: Opportunity) -> dict:
    return {
        "id": opp.id,
        "title": opp.title,
        "stage": opp.stage,
        "status": opp.status,
        "amount": opp.amount,
        "currency": opp.currency,
        "close_date": opp.close_date.isoformat() if opp.close_date else None,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
    }


def _email_request_to_dict(email: EmailRequest) -> dict:
    return {
        "id": email.id,
        "message_id": email.message_id,
        "from_address": email.from_address,
        "subject": email.subject,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "status": email.status,
    }
