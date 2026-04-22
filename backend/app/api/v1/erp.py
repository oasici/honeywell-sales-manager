"""REST endpoints for the ERP Connector Platform.

All routes are gated by:
    - FEATURE_ERP_CONNECTOR flag (administrative lockout).
    - require_role(ADMIN) dependency for write actions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.database import async_session, get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.erp import (
    ERPConnection,
    ERPEntityMapping,
    ERPSyncConflict,
    ERPSyncJob,
)
from app.models.user import User
from app.schemas.erp import (
    CONFLICT_ACTIONS,
    ENTITY_TYPES,
    ERP_TYPES,
    SYNC_MODES,
    ERPConflictOut,
    ERPConflictResolve,
    ERPConnectionCreate,
    ERPConnectionOut,
    ERPConnectionUpdate,
    ERPMappingRow,
    ERPSyncJobOut,
    ERPSyncTrigger,
    ERPTestConnectionResult,
)
from app.services.erp import build_connector
from app.services.erp.base import ConnectorError
from app.services.erp.invoice_push import InvoicePushError, push_quote_as_invoice
from app.services.erp.orchestrator import ERPOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/erp", tags=["ERP"])


# ── Guards ──────────────────────────────────────────────────────────────────

def _require_flag() -> None:
    if not settings.FEATURE_ERP_CONNECTOR:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ERP connector is disabled on this environment",
        )


def _get_orchestrator() -> ERPOrchestrator:
    return ERPOrchestrator(session_factory=async_session, redis=None)


# ── Connection CRUD ─────────────────────────────────────────────────────────

@router.get("/connections", response_model=list[ERPConnectionOut])
async def list_connections(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> list[ERPConnection]:
    _require_flag()
    rows = (await db.execute(select(ERPConnection).order_by(ERPConnection.id.desc()))).scalars().all()
    return list(rows)


@router.post(
    "/connections",
    response_model=ERPConnectionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    body: ERPConnectionCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> ERPConnection:
    _require_flag()
    if body.type not in ERP_TYPES:
        raise HTTPException(400, f"Unsupported ERP type: {body.type}")

    connection = ERPConnection(
        type=body.type,
        name=body.name,
        endpoint=body.endpoint,
        credentials_encrypted=encrypt_json(body.credentials),
        sync_cron=body.sync_cron,
        config_json=json.dumps(body.config) if body.config else None,
        created_by=current_user.id,
    )
    db.add(connection)
    await db.flush()
    await db.commit()
    await db.refresh(connection)
    logger.info("erp.connection.created id=%s type=%s actor=%s", connection.id, connection.type, current_user.id)
    return connection


@router.get("/connections/{conn_id}", response_model=ERPConnectionOut)
async def get_connection(
    conn_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> ERPConnection:
    _require_flag()
    row = await db.get(ERPConnection, conn_id)
    if not row:
        raise HTTPException(404, "Connection not found")
    return row


@router.put("/connections/{conn_id}", response_model=ERPConnectionOut)
async def update_connection(
    conn_id: int,
    body: ERPConnectionUpdate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> ERPConnection:
    _require_flag()
    row = await db.get(ERPConnection, conn_id)
    if not row:
        raise HTTPException(404, "Connection not found")
    if body.name is not None:
        row.name = body.name
    if body.endpoint is not None:
        row.endpoint = body.endpoint
    if body.sync_cron is not None:
        row.sync_cron = body.sync_cron
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.credentials is not None:
        row.credentials_encrypted = encrypt_json(body.credentials)
    if body.config is not None:
        row.config_json = json.dumps(body.config)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/connections/{conn_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=None)
async def delete_connection(
    conn_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
):
    _require_flag()
    row = await db.get(ERPConnection, conn_id)
    if not row:
        return
    await db.delete(row)
    await db.commit()


# ── Test + Sync ─────────────────────────────────────────────────────────────

@router.post("/connections/{conn_id}/test", response_model=ERPTestConnectionResult)
async def test_connection(
    conn_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> ERPTestConnectionResult:
    _require_flag()
    row = await db.get(ERPConnection, conn_id)
    if not row:
        raise HTTPException(404, "Connection not found")
    try:
        connector = build_connector(row)
        details = await connector.test_connection()
        return ERPTestConnectionResult(ok=True, details=details)
    except ConnectorError as exc:
        return ERPTestConnectionResult(ok=False, error=str(exc))


@router.post(
    "/connections/{conn_id}/sync",
    response_model=ERPSyncJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_sync(
    conn_id: int,
    body: ERPSyncTrigger,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> ERPSyncJob:
    _require_flag()
    row = await db.get(ERPConnection, conn_id)
    if not row:
        raise HTTPException(404, "Connection not found")
    if body.entity not in ENTITY_TYPES:
        raise HTTPException(400, f"Unknown entity: {body.entity}")
    if body.mode not in SYNC_MODES:
        raise HTTPException(400, f"Unknown mode: {body.mode}")

    orchestrator = _get_orchestrator()
    job_id = await orchestrator.trigger(
        connection_id=conn_id,
        entity=body.entity,
        mode=body.mode,
        actor_id=current_user.id,
        triggered_by="manual",
    )
    job = await db.get(ERPSyncJob, job_id)
    if not job:
        raise HTTPException(500, "Failed to queue sync job")
    return job


@router.get("/connections/{conn_id}/jobs", response_model=list[ERPSyncJobOut])
async def list_jobs(
    conn_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[ERPSyncJob]:
    _require_flag()
    stmt = (
        select(ERPSyncJob)
        .where(ERPSyncJob.connection_id == conn_id)
        .order_by(desc(ERPSyncJob.queued_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


# ── Mappings + Conflicts ────────────────────────────────────────────────────

@router.get(
    "/connections/{conn_id}/mappings",
    response_model=list[ERPMappingRow],
)
async def list_mappings(
    conn_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    entity_type: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[ERPEntityMapping]:
    _require_flag()
    stmt = select(ERPEntityMapping).where(ERPEntityMapping.connection_id == conn_id)
    if entity_type:
        stmt = stmt.where(ERPEntityMapping.entity_type == entity_type)
    stmt = stmt.order_by(desc(ERPEntityMapping.last_synced_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/conflicts", response_model=list[ERPConflictOut])
async def list_conflicts(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    status_filter: str = Query("pending", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ERPSyncConflict]:
    _require_flag()
    stmt = (
        select(ERPSyncConflict)
        .where(ERPSyncConflict.status == status_filter)
        .order_by(desc(ERPSyncConflict.detected_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.post(
    "/conflicts/{conflict_id}/resolve",
    response_model=ERPConflictOut,
)
async def resolve_conflict(
    conflict_id: int,
    body: ERPConflictResolve,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> ERPSyncConflict:
    _require_flag()
    row = await db.get(ERPSyncConflict, conflict_id)
    if not row:
        raise HTTPException(404, "Conflict not found")
    if body.action not in CONFLICT_ACTIONS:
        raise HTTPException(400, f"Unknown action: {body.action}")
    if row.status != "pending":
        raise HTTPException(409, "Conflict already resolved")

    # Apply the resolution to the domain row. "hss_wins" and "dismiss" leave
    # the HSS copy untouched; "erp_wins" overwrites with the erp_snapshot;
    # "merge" expects ``merged_payload`` in the request body and applies it.
    if body.action in ("erp_wins", "merge"):
        target_payload = (
            body.merged_payload
            if body.action == "merge" and body.merged_payload
            else _safe_json(row.erp_snapshot)
        )
        await _apply_resolution_payload(
            db,
            entity_type=row.entity_type,
            internal_id=row.internal_id,
            payload=target_payload or {},
        )

    row.status = f"resolved_{body.action}" if body.action != "dismiss" else "dismissed"
    row.resolved_at = datetime.now(timezone.utc)
    row.resolved_by = current_user.id
    row.resolution_note = body.note

    await db.commit()
    await db.refresh(row)
    logger.info(
        "erp.conflict.resolved id=%s action=%s actor=%s",
        row.id, body.action, current_user.id,
    )
    return row


def _safe_json(value: str) -> dict:
    try:
        return json.loads(value) if value else {}
    except json.JSONDecodeError:
        return {}


async def _apply_resolution_payload(
    db: AsyncSession, *, entity_type: str, internal_id: int, payload: dict
) -> None:
    """Write the chosen payload back into the HSS domain table."""
    if entity_type == "customer":
        from app.models.customer import Customer

        customer = await db.get(Customer, internal_id)
        if not customer:
            return
        if payload.get("name"):
            customer.name = payload["name"]
        if payload.get("email"):
            customer.email = payload["email"]
        if payload.get("phone") is not None:
            customer.phone = payload.get("phone")
        if payload.get("address") is not None:
            customer.address = payload.get("address")
        if payload.get("tax_number") is not None:
            customer.tax_id = payload.get("tax_number")
        return

    if entity_type == "product":
        from app.models.spare_part import SparePart

        part = await db.get(SparePart, internal_id)
        if not part:
            return
        if payload.get("name"):
            part.name_tr = payload["name"]
        if payload.get("unit_price") is not None:
            part.transfer_price = payload["unit_price"]
        if payload.get("currency"):
            part.price_currency = payload["currency"]
        return


# ── Quote → ERP invoice push ────────────────────────────────────────────────


class InvoicePushRequest(BaseModel):
    connection_id: int
    quote_id: int


class InvoicePushResult(BaseModel):
    external_id: str
    already_pushed: bool


@router.post("/invoices/push", response_model=InvoicePushResult)
async def push_invoice(
    body: InvoicePushRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> InvoicePushResult:
    """Push an accepted quote into the selected ERP as an invoice.

    Idempotent: re-running the endpoint for the same quote/connection returns
    the previously stored external id without a second write.
    """
    _require_flag()
    try:
        result = await push_quote_as_invoice(
            db,
            quote_id=body.quote_id,
            connection_id=body.connection_id,
            actor_id=current_user.id,
        )
        await db.commit()
    except InvoicePushError as exc:
        raise HTTPException(400, str(exc)) from exc
    return InvoicePushResult(**result)


# ── Debug / introspection ───────────────────────────────────────────────────

@router.get("/connections/{conn_id}/credentials-check")
async def credentials_probe(
    conn_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the *keys* of stored credentials (never the values)."""
    _require_flag()
    row = await db.get(ERPConnection, conn_id)
    if not row:
        raise HTTPException(404, "Connection not found")
    try:
        keys = sorted(decrypt_json(row.credentials_encrypted).keys())
    except ValueError:
        keys = []
    return {"connection_id": conn_id, "credential_keys": keys}
