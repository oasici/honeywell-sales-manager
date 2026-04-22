"""Read-only REST endpoints for the field-level audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.field_audit import FieldAuditLog
from app.models.user import User

router = APIRouter(prefix="/field-audit", tags=["Audit"])


class FieldAuditRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    actor_id: int | None
    actor_kind: str
    changed_at: datetime
    correlation_id: str | None


def _require_flag() -> None:
    if not settings.FEATURE_FIELD_AUDIT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field audit is disabled on this environment",
        )


@router.get("/", response_model=list[FieldAuditRow])
async def list_field_audit(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    entity_type: str | None = Query(None, max_length=64),
    entity_id: int | None = None,
    field_name: str | None = Query(None, max_length=96),
    actor_id: int | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[FieldAuditLog]:
    _require_flag()
    stmt = select(FieldAuditLog)
    if entity_type:
        stmt = stmt.where(FieldAuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(FieldAuditLog.entity_id == entity_id)
    if field_name:
        stmt = stmt.where(FieldAuditLog.field_name == field_name)
    if actor_id is not None:
        stmt = stmt.where(FieldAuditLog.actor_id == actor_id)
    stmt = stmt.order_by(desc(FieldAuditLog.changed_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/entities/{entity_type}/{entity_id}", response_model=list[FieldAuditRow])
async def entity_history(
    entity_type: str,
    entity_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[FieldAuditLog]:
    _require_flag()
    stmt = (
        select(FieldAuditLog)
        .where(
            FieldAuditLog.entity_type == entity_type,
            FieldAuditLog.entity_id == entity_id,
        )
        .order_by(desc(FieldAuditLog.changed_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)
