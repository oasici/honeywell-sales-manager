"""AI attribute API.

Plan adoption — Phase 2 / Sprint 8. Admin-defined fields populated by
an LLM; values cached and surfaced alongside human-edited custom fields.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services import ai_attribute_service
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/ai-attributes", tags=["AI Attributes"])


def _require_ai_attributes() -> None:
    """Round-8 R8-FLAG-3 — paired feature gate."""
    if not settings.FEATURE_AI_ATTRIBUTES:
        raise HTTPException(status_code=404, detail="Not found")


class DefinitionCreate(BaseModel):
    entity_type: str = Field(..., max_length=30)
    key: str = Field(..., max_length=80)
    label: str = Field(..., max_length=200)
    description: str | None = None
    data_type: str = Field("text")
    prompt_template: str
    refresh_hours: int = 24


class DefinitionPatch(BaseModel):
    label: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    is_active: bool | None = None
    refresh_hours: int | None = None


class GenerateBody(BaseModel):
    entity_id: int
    context: dict[str, str] | None = None


@router.get("/definitions", response_model=PaginatedResponse[dict])
async def list_definitions(
    entity_type: str | None = Query(None),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_attributes),
):
    items = await ai_attribute_service.list_definitions(
        db, current_user, entity_type=entity_type, active_only=active_only
    )
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}


@router.post("/definitions", status_code=201)
async def create_definition(
    body: DefinitionCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_attributes),
):
    return await ai_attribute_service.create_definition(
        db,
        current_user,
        entity_type=body.entity_type,
        key=body.key,
        label=body.label,
        description=body.description,
        data_type=body.data_type,
        prompt_template=body.prompt_template,
        refresh_hours=body.refresh_hours,
    )


@router.patch("/definitions/{definition_id}")
async def update_definition(
    definition_id: int,
    body: DefinitionPatch,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_attributes),
):
    return await ai_attribute_service.update_definition(
        db, current_user, definition_id, **body.model_dump(exclude_unset=True)
    )


@router.get("/values", response_model=PaginatedResponse[dict])
async def list_values(
    entity_type: str = Query(...),
    entity_id: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_attributes),
):
    items = await ai_attribute_service.list_values(
        db, current_user, entity_type=entity_type, entity_id=entity_id
    )
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}


@router.post("/definitions/{definition_id}/generate", status_code=201)
async def generate(
    definition_id: int,
    body: GenerateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_attributes),
):
    return await ai_attribute_service.generate_value(
        db,
        current_user,
        definition_id=definition_id,
        entity_id=body.entity_id,
        context=body.context,
    )
