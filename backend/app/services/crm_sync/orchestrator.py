"""Sync orchestrator — drives an adapter through a single sync job.

Pull strategy: list_records since the last successful sync; for each
record, upsert into the internal entity (Customer / Opportunity) via
``crm_record_links`` for idempotency. Push strategy: walk dirty
internal rows and call ``adapter.push_record``.

V9 MVP scope: ``account → customers`` pull only + ``opportunity →
opportunities`` pull only. Push direction lands in V10.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.v9_crm_sync import CrmConnection, CrmRecordLink, CrmSyncJob
from app.services.crm_sync.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    ConnectorTransientError,
    SyncResult,
)
from app.services.crm_sync.factory import get_adapter

logger = logging.getLogger(__name__)


_SUPPORTED_ENTITY_TYPES = ("account", "opportunity")


async def run_sync_job(
    db: AsyncSession,
    *,
    connection_id: int,
    entity_type: str,
    test_mode: bool = False,
) -> CrmSyncJob:
    """Execute a sync job end-to-end and persist a CrmSyncJob row.

    Idempotent on (connection_id, entity_type, batch) via
    ``crm_record_links`` — re-running a job for the same window
    updates the same internal rows instead of creating duplicates.
    """
    if entity_type not in _SUPPORTED_ENTITY_TYPES:
        raise ConnectorError(f"Unsupported entity_type: {entity_type}")

    connection = await db.get(CrmConnection, connection_id)
    if connection is None or not connection.is_active:
        raise ConnectorError("Connection not found or inactive")

    job = CrmSyncJob(
        connection_id=connection_id,
        entity_type=entity_type,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    errors: list[dict] = []
    pulled = 0

    try:
        adapter = get_adapter(connection, test_mode=test_mode)
        records = list(
            adapter.list_records(
                entity_type=entity_type,
                since=connection.last_sync_at,
                limit=200,
            )
        )

        for rec in records:
            try:
                if entity_type == "account":
                    await _upsert_account(db, connection_id, rec)
                elif entity_type == "opportunity":
                    await _upsert_opportunity(db, connection_id, rec)
                pulled += 1
            except Exception as exc:
                logger.warning(
                    "v9 crm sync upsert failed external=%s err=%s",
                    rec.external_id,
                    exc,
                )
                errors.append({"external_id": rec.external_id, "error": str(exc)})

        connection.last_sync_at = datetime.now(timezone.utc)
        connection.sync_state = "idle"
    except ConnectorAuthError as exc:
        connection.sync_state = "auth_error"
        errors.append({"error": str(exc), "kind": "auth"})
    except ConnectorRateLimitError as exc:
        connection.sync_state = "rate_limited"
        errors.append({"error": str(exc), "kind": "rate_limit"})
    except ConnectorTransientError as exc:
        connection.sync_state = "transient_error"
        errors.append({"error": str(exc), "kind": "transient"})
    except ConnectorError as exc:
        connection.sync_state = "error"
        errors.append({"error": str(exc), "kind": "connector"})

    job.items_pulled = pulled
    job.items_failed = len(errors)
    job.status = "succeeded" if not errors else "partial" if pulled else "failed"
    job.finished_at = datetime.now(timezone.utc)
    if errors:
        job.error_log_json = json.dumps(errors[:50], ensure_ascii=False)

    await db.flush()
    return job


# ─────────────────────── upsert helpers ──────────────────────────────


async def _upsert_account(
    db: AsyncSession, connection_id: int, rec
) -> None:
    """Map an external Account → Customer row, idempotent by external_id."""
    link = (
        await db.execute(
            select(CrmRecordLink)
            .where(CrmRecordLink.connection_id == connection_id)
            .where(CrmRecordLink.internal_entity_type == "customer")
            .where(CrmRecordLink.external_id == rec.external_id)
        )
    ).scalar_one_or_none()

    name = (
        rec.fields.get("Name")
        or rec.fields.get("name")
        or f"CRM-{rec.external_id}"
    )
    industry = rec.fields.get("Industry") or rec.fields.get("industry")
    employee_count = rec.fields.get("NumberOfEmployees")
    try:
        employee_count = int(employee_count) if employee_count is not None else None
    except (TypeError, ValueError):
        employee_count = None
    email = rec.fields.get("Email") or rec.fields.get("email") or f"{rec.external_id}@crm.local"

    sig = _hash_signature(rec.fields)

    if link is None:
        # Round-15 Sprint 15k cohort 1 — Customer.tenant_id NOT NULL.
        # Inherit from the connection row (the connection itself is
        # tenant-scoped at the schema layer).
        connection = await db.get(CrmConnection, connection_id)
        derived_tenant_id = getattr(connection, "tenant_id", None) if connection else None

        cust = Customer(
            tenant_id=derived_tenant_id,
            name=name,
            company=name,
            email=email,
            phone=rec.fields.get("Phone") or rec.fields.get("phone"),
            address=rec.fields.get("BillingAddress") or "",
            tax_id="",
            industry=industry,
            employee_count=employee_count,
        )
        db.add(cust)
        await db.flush()
        db.add(
            CrmRecordLink(
                connection_id=connection_id,
                internal_entity_type="customer",
                internal_id=cust.id,
                external_id=rec.external_id,
                hash_signature=sig,
            )
        )
    else:
        cust = await db.get(Customer, link.internal_id)
        if cust is not None and link.hash_signature != sig:
            cust.name = name
            cust.company = name
            if hasattr(cust, "industry"):
                cust.industry = industry
            if hasattr(cust, "employee_count"):
                cust.employee_count = employee_count
            link.hash_signature = sig
            link.last_synced_at = datetime.now(timezone.utc)


async def _upsert_opportunity(
    db: AsyncSession, connection_id: int, rec
) -> None:
    """Map an external Opportunity/Deal → Opportunity row."""
    link = (
        await db.execute(
            select(CrmRecordLink)
            .where(CrmRecordLink.connection_id == connection_id)
            .where(CrmRecordLink.internal_entity_type == "opportunity")
            .where(CrmRecordLink.external_id == rec.external_id)
        )
    ).scalar_one_or_none()

    title = rec.fields.get("Name") or rec.fields.get("dealname") or f"CRM-{rec.external_id}"
    stage_raw = (rec.fields.get("StageName") or rec.fields.get("dealstage") or "prospecting").lower()
    stage = _normalize_stage(stage_raw)
    amount = rec.fields.get("Amount") or rec.fields.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None

    sig = _hash_signature(rec.fields)

    if link is None:
        # Best-effort: opportunity needs an owner_id; pick any user.
        from app.models.user import User

        owner_id = (
            await db.execute(select(User.id).limit(1))
        ).scalar_one_or_none()
        if owner_id is None:
            raise ConnectorError("Cannot create opportunity — no User in DB")
        # Round-15 Sprint 15k cohort 1 — Opportunity.tenant_id NOT
        # NULL. Inherit from the CRM connection (or the owner user
        # as a fallback).
        connection = await db.get(CrmConnection, connection_id)
        derived_tenant_id = getattr(connection, "tenant_id", None) if connection else None
        if derived_tenant_id is None:
            owner_row = await db.execute(
                select(User.tenant_id).where(User.id == int(owner_id))
            )
            derived_tenant_id = owner_row.scalar_one_or_none()

        opp = Opportunity(
            tenant_id=derived_tenant_id,
            customer_id=None,
            owner_id=int(owner_id),
            title=title,
            stage=stage,
            status="active" if stage not in {"closed_won", "closed_lost"} else "closed",
            amount=amount,
            currency="TRY",
        )
        db.add(opp)
        await db.flush()
        db.add(
            CrmRecordLink(
                connection_id=connection_id,
                internal_entity_type="opportunity",
                internal_id=opp.id,
                external_id=rec.external_id,
                hash_signature=sig,
            )
        )
    else:
        opp = await db.get(Opportunity, link.internal_id)
        if opp is not None and link.hash_signature != sig:
            opp.title = title
            opp.stage = stage
            if amount is not None:
                opp.amount = amount
            opp.status = "active" if stage not in {"closed_won", "closed_lost"} else "closed"
            link.hash_signature = sig
            link.last_synced_at = datetime.now(timezone.utc)


# ─────────────────────── small helpers ───────────────────────────────


def _normalize_stage(raw: str) -> str:
    """Map provider-specific stage strings → our enum values."""
    raw = (raw or "").lower().strip()
    mapping = {
        "prospecting": "prospecting",
        "qualification": "qualified",
        "qualified": "qualified",
        "needs analysis": "qualified",
        "value proposition": "qualified",
        "id. decision makers": "qualified",
        "perception analysis": "qualified",
        "proposal/price quote": "proposal",
        "proposal": "proposal",
        "appointmentscheduled": "qualified",
        "qualifiedtobuy": "qualified",
        "presentationscheduled": "qualified",
        "decisionmakerboughtin": "negotiation",
        "contractsent": "negotiation",
        "closedwon": "closed_won",
        "closedlost": "closed_lost",
        "closed won": "closed_won",
        "closed lost": "closed_lost",
        "negotiation/review": "negotiation",
        "negotiation": "negotiation",
    }
    return mapping.get(raw, "prospecting")


def _hash_signature(fields: dict) -> str:
    """Stable signature so we only update when content actually changed."""
    canonical = json.dumps(
        {k: v for k, v in fields.items() if not k.startswith("_")},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
