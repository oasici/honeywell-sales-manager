"""Custom fields API — user-defined fields for entities (admin self-service)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services.custom_field_service import CustomFieldService
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import CustomFieldDefinitionRow

router = APIRouter(prefix="/custom-fields", tags=["Custom Fields"])

VALID_ENTITY_TYPES = {"customer", "opportunity", "quote", "lead"}
VALID_FIELD_TYPES = {"text", "number", "date", "select", "checkbox"}


def _require_custom_fields():
    """Dependency: reject if FEATURE_CUSTOM_FIELDS is off."""
    if not settings.FEATURE_CUSTOM_FIELDS:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class CustomFieldCreate(BaseModel):
    entity_type: str = Field(..., max_length=30)
    field_name: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., max_length=20)
    options_json: str | None = None
    is_required: bool = False
    sort_order: int = 0


class CustomFieldValueSet(BaseModel):
    field_id: int
    value: str | float | None = None


# ── Endpoints ──


@router.get("/", response_model=PaginatedResponse[CustomFieldDefinitionRow])
async def list_custom_fields(
    entity_type: str = "customer",
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_custom_fields),
):
    """List custom field definitions for an entity type."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz varlik tipi. Gecerli tipler: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    service = CustomFieldService(db)
    fields = await service.get_fields(entity_type)
    total = len(fields)
    # Round-12 R12-API-1 — canonical pagination envelope.
    return {
        "items": fields,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/", status_code=201, response_model=dict)
async def create_custom_field(
    body: CustomFieldCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_custom_fields),
):
    """Create a new custom field definition (manager only)."""
    if body.entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz varlik tipi. Gecerli tipler: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    if body.field_type not in VALID_FIELD_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz alan tipi. Gecerli tipler: {', '.join(sorted(VALID_FIELD_TYPES))}",
        )

    service = CustomFieldService(db)
    try:
        field = await service.create_field(
            entity_type=body.entity_type,
            field_name=body.field_name,
            field_type=body.field_type,
            options_json=body.options_json,
            is_required=body.is_required,
            sort_order=body.sort_order,
            created_by=current_user.id,
        )
    except Exception:
        raise HTTPException(
            status_code=409,
            detail=f"Bu varlik tipi icin '{body.field_name}' alani zaten mevcut",
        )

    return {
        "message": "Ozel alan olusturuldu",
        "id": field.id,
        "field_name": field.field_name,
    }


@router.delete("/{field_id}", response_model=dict)
async def delete_custom_field(
    field_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_custom_fields),
):
    """Delete a custom field and all its values (manager only)."""
    service = CustomFieldService(db)
    is_ok = await service.delete_field(field_id)
    if not is_ok:
        raise HTTPException(status_code=404, detail="Ozel alan bulunamadi")
    return {"message": "Ozel alan silindi", "id": field_id}


@router.get("/values/{entity_type}/{entity_id}", response_model=dict)
async def get_custom_field_values(
    entity_type: str,
    entity_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_custom_fields),
):
    """Get all custom field values for a specific entity."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz varlik tipi. Gecerli tipler: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    service = CustomFieldService(db)
    values = await service.get_values(entity_type, entity_id)
    return {"entity_type": entity_type, "entity_id": entity_id, "values": values}


@router.post("/values/{entity_type}/{entity_id}", response_model=dict)
async def set_custom_field_value(
    entity_type: str,
    entity_id: int,
    body: CustomFieldValueSet,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_custom_fields),
):
    """Set a custom field value for a specific entity."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz varlik tipi. Gecerli tipler: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    service = CustomFieldService(db)
    try:
        value = await service.set_value(
            field_id=body.field_id,
            entity_type=entity_type,
            entity_id=entity_id,
            value=body.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {"message": "Deger kaydedildi", "id": value.id}
