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
from app.core.rate_limit import enforce_kvkk_export_rate_limit
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user

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


@router.get(
    "/export/csv",
    # Round-4 R4-RL-5 — bulk PII export must be rate-limited.
    dependencies=[Depends(enforce_kvkk_export_rate_limit)],
)
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


@router.get(
    "/data-export/{target_user_id}",
    # Round-4 R4-RL-5 — KVKK Article 15 disclosure path.
    dependencies=[Depends(enforce_kvkk_export_rate_limit)],
)
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
    # Cross-tenant target maps to 404 (KVKK Article 15 must not leak
    # cross-tenant existence).
    assert_same_tenant(
        user, current_user, exception_cls=lambda msg: HTTPException(status_code=404, detail=msg)
    )

    # All related-entity loads are tenant-scoped so a stale cross-tenant
    # FK (e.g., a user moved between tenants) cannot leak data either.
    audit_events = (
        await db.execute(
            scoped_for_user(
                select(AuditLog), current_user, column=AuditLog.tenant_id
            )
            .where(AuditLog.user_id == target_user_id)
            .order_by(AuditLog.created_at.desc())
        )
    ).scalars().all()

    created_customers = (
        await db.execute(
            scoped_for_user(
                select(Customer), current_user, column=Customer.tenant_id
            ).where(Customer.created_by == target_user_id)
        )
    ).scalars().all()

    owned_opportunities = (
        await db.execute(
            scoped_for_user(
                select(Opportunity), current_user, column=Opportunity.tenant_id
            ).where(Opportunity.owner_id == target_user_id)
        )
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
    """Public-safe user fields for KVKK export. No password hash.

    R5-API-2 — also exposes tenant_id / manager_id so the export
    bundle reflects the same shape as the live admin endpoints. The
    audit trail must be a strict superset of what's visible elsewhere
    to satisfy KVKK Article 15 (right of access) — anything the user
    sees in the SPA must be in the export too.
    """
    return {
        "id": user.id,
        "tenant_id": getattr(user, "tenant_id", None),
        "manager_id": getattr(user, "manager_id", None),
        "email": user.email,
        "full_name": getattr(user, "full_name", None),
        "role": getattr(user, "role", None),
        "is_active": getattr(user, "is_active", None),
        "email_setup_completed": getattr(user, "email_setup_completed", False),
        "password_change_required": getattr(user, "password_change_required", False),
        # User.created_at / updated_at are non-null columns; the direct
        # truthiness check is sufficient. Removed the redundant
        # getattr-with-default pattern (Gemini review on PR #41).
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


# R6-API-7 / R6-API-13 — KVKK Article 15 export must be a strict
# superset of what the user sees in the SPA. Pre-R6 these helpers
# returned 7 fields each while the canonical serializers returned
# 17+. Duplication produced silent drift every time round-4/5 added
# a column. Reuse the canonical serializers instead.
from app.api.v1.customers import _customer_to_dict as _customer_to_dict_canonical
from app.api.v1.opportunities import _opp_to_dict as _opportunity_to_dict_canonical
from app.api.v1.emails import _email_to_dict as _email_to_dict_canonical


def _customer_to_dict(customer: Customer) -> dict:
    return _customer_to_dict_canonical(customer)


def _opportunity_to_dict(opp: Opportunity) -> dict:
    return _opportunity_to_dict_canonical(opp)


def _email_request_to_dict(email: EmailRequest) -> dict:
    # Audit export wants the headers, not bodies (the body export is a
    # separate ``include_body=True`` flow).
    return _email_to_dict_canonical(email, include_body=False)
