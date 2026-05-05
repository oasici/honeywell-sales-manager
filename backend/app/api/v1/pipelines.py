"""Multi-Pipeline API — configurable sales pipeline CRUD."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.pipeline import Pipeline
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


def _require_multi_pipeline():
    """Dependency: reject if FEATURE_MULTI_PIPELINE is off."""
    if not settings.FEATURE_MULTI_PIPELINE:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    stages_json: Optional[str] = None
    description: Optional[str] = None
    is_default: bool = False


class PipelineUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    stages_json: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


# ── Serializer ──


def _serialize_pipeline(p: Pipeline) -> dict:
    return {
        "id": p.id,
        # R5-TEN-26 — round-trip tenant_id so the SPA can verify the
        # boundary (pattern from R4-DTO-5).
        "tenant_id": getattr(p, "tenant_id", None),
        "name": p.name,
        "stages_json": p.stages_json,
        "is_default": p.is_default,
        "description": p.description,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Endpoints ──


@router.get("/")
async def list_pipelines(
    _: None = Depends(_require_multi_pipeline),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pipelines visible to the caller's tenant."""
    stmt = scoped_for_user(
        select(Pipeline).order_by(Pipeline.is_default.desc(), Pipeline.name),
        current_user,
        column=Pipeline.tenant_id,
    )
    result = await db.execute(stmt)
    pipelines = result.scalars().all()
    return {"pipelines": [_serialize_pipeline(p) for p in pipelines]}


@router.post("/", status_code=201)
async def create_pipeline(
    body: PipelineCreate,
    _: None = Depends(_require_multi_pipeline),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new pipeline. Manager-only, tenant-scoped."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if body.is_default:
        # Only flip is_default off within the caller's tenant.
        await db.execute(
            scoped_for_user(
                update(Pipeline).values(is_default=False),
                current_user,
                column=Pipeline.tenant_id,
            )
        )

    pipeline = Pipeline(
        tenant_id=tenant_id,
        name=body.name,
        stages_json=body.stages_json,
        description=body.description,
        is_default=body.is_default,
        created_by=current_user.id,
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)
    return _serialize_pipeline(pipeline)


@router.get("/{pipeline_id}")
async def get_pipeline(
    pipeline_id: int,
    _: None = Depends(_require_multi_pipeline),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get pipeline detail."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise NotFoundException("Pipeline not found")
    # R5-TEN-26 — both "doesn't exist" and "lives in another tenant"
    # collapse to 404 so the API never leaks cross-tenant existence.
    assert_same_tenant(pipeline, current_user, exception_cls=NotFoundException)
    return _serialize_pipeline(pipeline)


@router.put("/{pipeline_id}")
async def update_pipeline(
    pipeline_id: int,
    body: PipelineUpdate,
    _: None = Depends(_require_multi_pipeline),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a pipeline. Manager-only, tenant-scoped."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise NotFoundException("Pipeline not found")
    assert_same_tenant(pipeline, current_user, exception_cls=NotFoundException)

    if body.name is not None:
        pipeline.name = body.name
    if body.stages_json is not None:
        pipeline.stages_json = body.stages_json
    if body.description is not None:
        pipeline.description = body.description
    if body.is_default is not None:
        if body.is_default:
            # Only un-default other pipelines in the caller's tenant.
            await db.execute(
                scoped_for_user(
                    update(Pipeline)
                    .where(Pipeline.id != pipeline_id)
                    .values(is_default=False),
                    current_user,
                    column=Pipeline.tenant_id,
                )
            )
        pipeline.is_default = body.is_default

    await db.commit()
    await db.refresh(pipeline)
    return _serialize_pipeline(pipeline)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(
    pipeline_id: int,
    _: None = Depends(_require_multi_pipeline),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a pipeline. Fails if opportunities reference it. Manager-only, tenant-scoped."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise NotFoundException("Pipeline not found")
    assert_same_tenant(pipeline, current_user, exception_cls=NotFoundException)

    opp_result = await db.execute(
        select(Opportunity.id).where(Opportunity.pipeline_id == pipeline_id).limit(1)
    )
    if opp_result.scalar_one_or_none() is not None:
        raise BadRequestException("Cannot delete pipeline: opportunities are assigned to it")

    await db.delete(pipeline)


@router.patch("/{pipeline_id}/set-default")
async def set_default_pipeline(
    pipeline_id: int,
    _: None = Depends(_require_multi_pipeline),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Set pipeline as default, clearing all others. Manager-only, tenant-scoped."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise NotFoundException("Pipeline not found")
    assert_same_tenant(pipeline, current_user, exception_cls=NotFoundException)

    # R5-TEN-26 — only flip the flag within the caller's tenant.
    await db.execute(
        scoped_for_user(
            update(Pipeline).values(is_default=False),
            current_user,
            column=Pipeline.tenant_id,
        )
    )
    pipeline.is_default = True
    await db.commit()
    await db.refresh(pipeline)
    return _serialize_pipeline(pipeline)
