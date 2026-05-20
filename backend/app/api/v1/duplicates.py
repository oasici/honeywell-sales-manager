"""Duplicate detection and merge API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException
from app.models.enums import UserRole
from app.models.user import User
from app.services.record_duplicate_service import RecordDuplicateService
from app.schemas.common import GenericDataResponse, ItemsResponse

router = APIRouter(prefix="/duplicates", tags=["Duplicate Management"])


class DuplicateCheckRequest(BaseModel):
    entity_type: str
    name: str
    company: str | None = None
    email: str | None = None
    exclude_id: int | None = None


class MergePreviewRequest(BaseModel):
    entity_type: str
    winner_id: int
    loser_id: int


class MergeRequest(BaseModel):
    entity_type: str
    winner_id: int
    loser_id: int


@router.post("/check", response_model=ItemsResponse)
async def check_duplicates(
    payload: DuplicateCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check for potential duplicate records using fuzzy matching."""
    if len(payload.name.strip()) < 2:
        raise BadRequestException("Isim en az 2 karakter olmalidir")

    service = RecordDuplicateService(db)
    matches = await service.find_duplicates(
        entity_type=payload.entity_type,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        exclude_id=payload.exclude_id,
    )
    # R7-API-4 — canonical pagination envelope; ``data`` legacy.
    total = len(matches)
    return {
        "items": matches,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        "data": matches,
    }


@router.post("/merge/preview", response_model=GenericDataResponse)
async def merge_preview(
    payload: MergePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview a merge operation showing side-by-side comparison."""
    if payload.winner_id == payload.loser_id:
        raise BadRequestException("Kazanan ve kaybeden ayni kayit olamaz")

    service = RecordDuplicateService(db)
    preview = await service.preview_merge(
        entity_type=payload.entity_type,
        winner_id=payload.winner_id,
        loser_id=payload.loser_id,
    )
    if "error" in preview:
        raise BadRequestException(preview["error"])
    return {"data": preview}


@router.post("/merge", response_model=GenericDataResponse)
async def merge_records(
    payload: MergeRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Execute a merge operation. Manager role required."""
    if payload.winner_id == payload.loser_id:
        raise BadRequestException("Kazanan ve kaybeden ayni kayit olamaz")

    service = RecordDuplicateService(db)
    result = await service.merge_records(
        entity_type=payload.entity_type,
        winner_id=payload.winner_id,
        loser_id=payload.loser_id,
        user_id=current_user.id,
        # Pass current_user so the service can run assert_same_tenant
        # on both records (audit TEN-8). Without this guard a manager
        # could merge a foreign tenant's customer into their own.
        current_user=current_user,
    )
    if "error" in result:
        raise BadRequestException(result["error"])
    return {"data": result}
