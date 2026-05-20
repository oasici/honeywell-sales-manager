from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.enums import UserRole
from app.models.user import User
from app.services.field_permission_service import FieldPermissionService

router = APIRouter(prefix="/field-permissions", tags=["Field Permissions"])


def _check_feature_enabled() -> None:
    if not settings.FEATURE_FIELD_PERMISSIONS:
        raise NotFoundException("Bu ozellik aktif degil")


class FieldPermissionCreate(BaseModel):
    role: str = Field(min_length=1, max_length=30)
    entity_type: str = Field(min_length=1, max_length=30)
    field_name: str = Field(min_length=1, max_length=100)
    access_level: str = Field(default="read", max_length=20)


class FieldPermissionResponse(BaseModel):
    id: int
    role: str
    entity_type: str
    field_name: str
    access_level: str
    created_at: str | None = None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[FieldPermissionResponse])
async def list_field_permissions(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
):
    """Alan izinlerini listele. Rol ve varlik tipine gore filtreleme destekler."""
    _check_feature_enabled()

    service = FieldPermissionService(db)
    permissions = await service.list_permissions(role=role, entity_type=entity_type)

    return [
        FieldPermissionResponse(
            id=p.id,
            role=p.role,
            entity_type=p.entity_type,
            field_name=p.field_name,
            access_level=p.access_level,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in permissions
    ]


@router.post("/", response_model=FieldPermissionResponse)
async def set_field_permission(
    body: FieldPermissionCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Alan izni olustur veya guncelle."""
    _check_feature_enabled()

    service = FieldPermissionService(db)
    try:
        permission = await service.set_permission(
            role=body.role,
            entity_type=body.entity_type,
            field_name=body.field_name,
            access_level=body.access_level,
        )
    except ValueError as e:
        raise BadRequestException(str(e))

    return FieldPermissionResponse(
        id=permission.id,
        role=permission.role,
        entity_type=permission.entity_type,
        field_name=permission.field_name,
        access_level=permission.access_level,
        created_at=permission.created_at.isoformat() if permission.created_at else None,
    )


@router.delete("/{permission_id}", response_model=dict)
async def delete_field_permission(
    permission_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Alan iznini sil."""
    _check_feature_enabled()

    service = FieldPermissionService(db)
    deleted = await service.delete_permission(permission_id)
    if not deleted:
        raise NotFoundException("Alan izni bulunamadi")

    return {"message": "Alan izni basariyla silindi"}
