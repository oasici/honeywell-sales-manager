import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/")
async def list_audit_logs(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(None, description="Filter by user ID"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    action: str | None = Query(None, description="Filter by action"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List audit logs with pagination and filters (sales_manager only)."""
    filters = _build_filters(user_id, entity_type, action)

    count_query = select(func.count(AuditLog.id))
    if filters:
        count_query = count_query.where(*filters)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    main_query = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if filters:
        main_query = main_query.where(*filters)

    result = await db.execute(main_query)
    logs = result.scalars().all()

    return {
        "items": [_audit_log_to_dict(log) for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


def _build_filters(
    user_id: int | None,
    entity_type: str | None,
    action: str | None,
) -> list:
    """Build SQLAlchemy filter conditions from query parameters."""
    filters = []
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if entity_type is not None:
        filters.append(AuditLog.entity_type == entity_type)
    if action is not None:
        filters.append(AuditLog.action == action)
    return filters


def _audit_log_to_dict(log: AuditLog) -> dict:
    """Convert AuditLog to a dictionary response."""
    return {
        "id": log.id,
        "user_id": log.user_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "changes": log.changes,
        "ip_address": log.ip_address,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
