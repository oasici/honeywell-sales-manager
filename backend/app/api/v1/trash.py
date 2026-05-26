"""F-007 wire — soft-delete restore + Trash listing.

Existing DELETE endpoints on each entity router (customers, leads,
quotes, …) continue to do their thing. This module adds the *reverse*
direction:

    GET    /trash/{entity}                — list soft-deleted rows
    POST   /trash/{entity}/{id}/restore   — un-tombstone

``entity`` is one of: customers, leads, opportunities, quotes,
contracts, invoices, email_requests. Restricted to operations sub-
roles (F-011). Tenant-scoped. Audited.

The existing DELETE endpoints don't need to change in this PR —
``mark_deleted`` from app/services/soft_delete.py is what they
should call (we'll migrate them one router at a time in follow-on
work). Until then, this restore endpoint still works against any
row that was soft-deleted via the model column directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/trash", tags=["Soft-Delete / Trash"])


_ALLOWED_ENTITIES = {
    "customers", "leads", "opportunities", "quotes",
    "contracts", "invoices", "email_requests",
}


def _require_ops(user: User) -> None:
    role = getattr(user, "role", None)
    if role not in {
        "operations", "sales_manager",
        "ops_users", "ops_data", "ops_billing",
    }:
        raise HTTPException(403, detail="trash_requires_ops_or_manager")


def _validate_entity(entity: str) -> None:
    if entity not in _ALLOWED_ENTITIES:
        raise HTTPException(
            400,
            detail={
                "code": "unknown_entity",
                "allowed": sorted(_ALLOWED_ENTITIES),
            },
        )


@router.get("/{entity}")
async def list_trashed(
    entity: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return soft-deleted rows for ``entity`` within the user's tenant.

    Default 100-row limit. Operators with a long backlog can paginate
    via offset (not needed yet at 20-30 user scale)."""
    _require_ops(current_user)
    _validate_entity(entity)
    limit = max(1, min(int(limit), 500))
    tenant_id = getattr(current_user, "tenant_id", None)
    sql = (
        f"SELECT id, deleted_at, deleted_by, delete_reason "
        f"FROM {entity} "
        f"WHERE deleted_at IS NOT NULL"
    )
    params = {"limit": limit}
    if tenant_id is not None:
        sql += " AND tenant_id = :tid"
        params["tid"] = tenant_id
    sql += " ORDER BY deleted_at DESC LIMIT :limit"
    rows = (await db.execute(text(sql), params)).mappings().all()
    return {"entity": entity, "items": [dict(r) for r in rows], "total": len(rows)}


@router.post("/{entity}/{id}/restore")
async def restore_entity(
    entity: str,
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Un-tombstone a soft-deleted row.

    Tenant-scoped: a foreign-tenant row returns 404, not 403, to
    avoid leaking existence (F-020 pattern).
    Operations + sales_manager only.
    """
    _require_ops(current_user)
    _validate_entity(entity)
    tenant_id = getattr(current_user, "tenant_id", None)

    # Tenant-aware single-query check; same constant-time approach
    # as F-020.
    where = "id = :id AND deleted_at IS NOT NULL"
    params: dict = {"id": id}
    if tenant_id is not None:
        where += " AND tenant_id = :tid"
        params["tid"] = tenant_id

    res = await db.execute(
        text(
            f"UPDATE {entity} "
            f"SET deleted_at = NULL, deleted_by = NULL, delete_reason = NULL "
            f"WHERE {where} "
            f"RETURNING id"
        ),
        params,
    )
    if (res.rowcount or 0) == 0:
        raise HTTPException(404, detail=f"{entity}_not_found_or_not_deleted")
    await db.flush()
    logger.info(
        "Soft-delete restored: entity=%s id=%d by user=%d",
        entity, id, current_user.id,
    )
    return {"restored": True, "entity": entity, "id": id}
