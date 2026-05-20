"""Self-service report builder endpoints."""
from __future__ import annotations

import json
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.report import ReportTemplate
from app.models.report_folder import ReportFolder
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import ReportFolderRow, ReportTemplateRow
from app.schemas.report import (
    AvailableColumnsResponse,
    FolderEnvelope,
    ReportExecutionEnvelope,
    ReportTemplateEnvelope,
    ScheduleResponse,
)
from app.services.report_engine import (
    ALLOWED_COLUMNS,
    ENTITY_JOINS,
    ENTITY_MODEL_MAP,
    ReportEngine,
)

router = APIRouter(prefix="/reports", tags=["Reports V2"])


def _check_feature_flag() -> None:
    """Raise 403 if report builder feature is disabled."""
    if not settings.FEATURE_REPORT_BUILDER:
        raise ForbiddenException("Rapor olusturucu ozelligi su anda devre disi")


# ── Schemas ──


class ReportFolderCreate(BaseModel):
    name: str = Field(max_length=200, min_length=1)
    parent_id: int | None = None
    is_shared: bool = False


class ReportFolderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    parent_id: int | None = None
    is_shared: bool | None = None


class ReportTemplateCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    entity_type: str = Field(pattern="^(quote|opportunity|customer|email)$")
    columns_json: str
    filters_json: str | None = None
    group_by: str | None = None
    sort_by: str | None = None
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    chart_type: str | None = Field(default=None, pattern="^(bar|line|pie|table)$")
    is_public: bool = False


class ReportTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    columns_json: str | None = None
    filters_json: str | None = None
    group_by: str | None = None
    sort_by: str | None = None
    sort_order: str | None = Field(default=None, pattern="^(asc|desc)$")
    chart_type: str | None = Field(default=None, pattern="^(bar|line|pie|table)$")
    is_public: bool | None = None


class ReportTemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None
    entity_type: str
    columns_json: str
    filters_json: str | None
    group_by: str | None
    sort_by: str | None
    sort_order: str
    chart_type: str | None
    is_system: bool
    created_by: int | None
    is_public: bool
    # Round-8 R8-CAST-1 — round-trip last_run_at so the SavedReportsPage
    # can drop its `as unknown as { last_run_at?: string }` cast.
    last_run_at: datetime | None = None

    model_config = {"from_attributes": True}


class InlineReportRequest(BaseModel):
    entity_type: str = Field(pattern="^(quote|opportunity|customer|email)$")
    columns: list[str]
    filters: list[dict] | None = None
    group_by: str | None = None
    sort_by: str | None = None
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    # Round-15 audit F-020 — capped at 200 per CLAUDE.md pagination
    # contract. Bulk exports go through ``/reports/export`` (streaming).
    limit: int = Field(default=1000, ge=1, le=5000)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=200)


# ── Folder CRUD ──


@router.get("/folders", response_model=PaginatedResponse[ReportFolderRow])
async def list_folders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List report folders: user's own + shared, scoped to caller's tenant.

    Round-5 Phase 7 — canonical pagination envelope. ``data`` is kept
    additively to bridge in-flight SPA builds.
    """
    _check_feature_flag()
    import math as _math

    # R5-TEN-28 — pre-R5 a folder marked is_shared=True was visible
    # from any tenant. Scope by tenant_id so shared just means
    # "shared within my tenant".
    from app.services.tenant_context import scoped_for_user as _scoped_for_user

    stmt = _scoped_for_user(
        select(ReportFolder).where(
            or_(
                ReportFolder.owner_id == current_user.id,
                ReportFolder.is_shared.is_(True),
            )
        ).order_by(ReportFolder.name),
        current_user,
        column=ReportFolder.tenant_id,
    )

    count_result = await db.execute(
        select(sa_func.count()).select_from(stmt.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(stmt.offset(offset).limit(page_size))
    folders = result.scalars().all()

    items = [
        {
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "owner_id": f.owner_id,
            "is_shared": f.is_shared,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in folders
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
        # Additive legacy key for in-flight consumers.
        "data": items,
    }


@router.post("/folders", status_code=201, response_model=FolderEnvelope)
async def create_folder(
    body: ReportFolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a report folder."""
    _check_feature_flag()

    from app.services.tenant_context import assert_same_tenant as _assert_same_tenant

    if body.parent_id:
        parent = (await db.execute(
            select(ReportFolder).where(ReportFolder.id == body.parent_id)
        )).scalar_one_or_none()
        if not parent:
            raise NotFoundException("Ust klasor bulunamadi")
        # R5-TEN-28 — block hanging subfolders off another tenant's folder.
        _assert_same_tenant(parent, current_user, exception_cls=NotFoundException)

    folder = ReportFolder(
        # R5-TEN-28 — stamp tenant on the row so listing is bounded.
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        parent_id=body.parent_id,
        owner_id=current_user.id,
        is_shared=body.is_shared,
    )
    db.add(folder)
    await db.flush()
    await db.refresh(folder)

    return {
        "data": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "owner_id": folder.owner_id,
            "is_shared": folder.is_shared,
        },
    }


@router.put("/folders/{folder_id}", response_model=FolderEnvelope)
async def update_folder(
    folder_id: int,
    body: ReportFolderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a report folder."""
    _check_feature_flag()

    from app.services.tenant_context import assert_same_tenant as _assert_same_tenant

    result = await db.execute(
        select(ReportFolder).where(ReportFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise NotFoundException("Klasor bulunamadi")
    # R5-TEN-28 — tenant boundary first; existence-leaking would
    # otherwise reveal that some folder_id lives in another tenant.
    _assert_same_tenant(folder, current_user, exception_cls=NotFoundException)

    is_owner = folder.owner_id == current_user.id
    is_manager = current_user.role == "sales_manager"
    if not is_owner and not is_manager:
        raise ForbiddenException("Bu klasore erisim yetkiniz yok")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(folder, key, value)

    await db.flush()
    await db.refresh(folder)

    return {
        "data": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "is_shared": folder.is_shared,
        },
    }


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report folder."""
    _check_feature_flag()

    from app.services.tenant_context import assert_same_tenant as _assert_same_tenant

    result = await db.execute(
        select(ReportFolder).where(ReportFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise NotFoundException("Klasor bulunamadi")
    # R5-TEN-28 — tenant gate.
    _assert_same_tenant(folder, current_user, exception_cls=NotFoundException)

    is_owner = folder.owner_id == current_user.id
    is_manager = current_user.role == "sales_manager"
    if not is_owner and not is_manager:
        raise ForbiddenException("Bu klasoru silme yetkiniz yok")

    await db.delete(folder)


# ── Template CRUD ──


@router.get("/templates", response_model=PaginatedResponse[ReportTemplateRow])
async def list_templates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List report templates: user's own + public + system (tenant-scoped).

    Round-5 Phase 7 — canonical pagination envelope. ``data`` is kept
    additively to bridge in-flight SPA builds.
    """
    _check_feature_flag()
    import math as _math

    from app.services.tenant_context import scoped_for_user

    # Round-4 R4-TEN-14 — restrict the public/owner list to the
    # caller's tenant. System templates (tenant_id IS NULL) remain
    # visible to everyone since they're shipped with the product.
    stmt = scoped_for_user(
        select(ReportTemplate),
        current_user,
        column=ReportTemplate.tenant_id,
    ).where(
        or_(
            ReportTemplate.created_by == current_user.id,
            ReportTemplate.is_public.is_(True),
            ReportTemplate.is_system.is_(True),
        )
    )

    count_result = await db.execute(
        select(sa_func.count()).select_from(stmt.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(stmt.offset(offset).limit(page_size))
    templates = result.scalars().all()

    items = [ReportTemplateResponse.model_validate(t) for t in templates]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
        # Additive legacy key for in-flight consumers.
        "data": items,
    }


@router.post("/templates", status_code=201, response_model=ReportTemplateEnvelope)
async def create_template(
    body: ReportTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a report template."""
    _check_feature_flag()
    _validate_columns_json(body.entity_type, body.columns_json)

    if body.filters_json:
        _validate_filters_json(body.filters_json)

    template = ReportTemplate(
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        description=body.description,
        entity_type=body.entity_type,
        columns_json=body.columns_json,
        filters_json=body.filters_json,
        group_by=body.group_by,
        sort_by=body.sort_by,
        sort_order=body.sort_order,
        chart_type=body.chart_type,
        is_public=body.is_public,
        created_by=current_user.id,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)

    return {"data": ReportTemplateResponse.model_validate(template)}


@router.put("/templates/{template_id}", response_model=ReportTemplateEnvelope)
async def update_template(
    template_id: int,
    body: ReportTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a report template."""
    _check_feature_flag()

    template = await _get_user_template(db, template_id, current_user)

    if template.is_system:
        raise ForbiddenException("Sistem sablonlari duzenlenemez")

    update_data = body.model_dump(exclude_unset=True)

    if "columns_json" in update_data and update_data["columns_json"] is not None:
        _validate_columns_json(template.entity_type, update_data["columns_json"])

    if "filters_json" in update_data and update_data["filters_json"] is not None:
        _validate_filters_json(update_data["filters_json"])

    for key, value in update_data.items():
        setattr(template, key, value)

    await db.flush()
    await db.refresh(template)

    return {"data": ReportTemplateResponse.model_validate(template)}


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report template (not system ones)."""
    _check_feature_flag()

    template = await _get_user_template(db, template_id, current_user)

    if template.is_system:
        raise ForbiddenException("Sistem sablonlari silinemez")

    await db.delete(template)


# ── Execution ──


@router.post(
    "/templates/{template_id}/execute",
    response_model=ReportExecutionEnvelope,
)
async def execute_template(
    template_id: int,
    page: int = Query(default=1, ge=1),
    # Round-15 audit F-020 — capped at 200 per CLAUDE.md.
    page_size: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a saved report template."""
    _check_feature_flag()

    offset = (page - 1) * page_size
    engine = ReportEngine(db)
    result = await engine.execute_report(
        template_id, current_user, limit=page_size, offset=offset
    )
    result["page"] = page
    result["page_size"] = page_size
    return {"data": result}


@router.post("/preview", response_model=ReportExecutionEnvelope)
async def preview_report(
    body: InlineReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a report with inline parameters (no save)."""
    _check_feature_flag()

    offset = (body.page - 1) * body.page_size
    engine = ReportEngine(db)
    result = await engine.execute_inline(
        entity_type=body.entity_type,
        columns=body.columns,
        current_user=current_user,
        filters=body.filters,
        group_by=body.group_by,
        sort_by=body.sort_by,
        sort_order=body.sort_order,
        limit=body.page_size,
        offset=offset,
    )
    result["page"] = body.page
    result["page_size"] = body.page_size
    return {"data": result}


# Round-15 N15-API-1: response_model exempt (returns non-JSON: file/redirect/stream)
@router.get("/templates/{template_id}/export")
async def export_template(
    template_id: int,
    format: str = Query(default="csv", pattern="^csv$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export report as CSV."""
    _check_feature_flag()

    engine = ReportEngine(db)
    csv_content = await engine.export_csv(template_id, current_user)

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report_{template_id}.csv"},
    )


# Round-15 N15-API-1: response_model exempt (returns non-JSON: file/redirect/stream)
@router.get("/templates/{template_id}/export-excel")
async def export_template_excel(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export report results as an Excel (.xlsx) file."""
    _check_feature_flag()

    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=501, detail="openpyxl yuklu degil")

    # R7-TEN-3 — pre-fix this re-loaded the template via a bare SELECT,
    # leaking the foreign tenant's report.name into the worksheet title
    # and Content-Disposition header even though engine.execute_report
    # itself was tenant-safe. Use the canonical helper that runs
    # assert_same_tenant before any other work.
    report = await _get_user_template(db, template_id, current_user)

    engine = ReportEngine(db)
    result = await engine.execute_report(template_id, current_user, limit=5000, offset=0)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report.name[:31]

    rows: list[dict] = result.get("rows", [])
    headers: list[str] = result.get("columns", list(rows[0].keys()) if rows else [])
    if headers:
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    safe_name = report.name.replace("/", "-").replace("\\", "-")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.xlsx"'},
    )


@router.get("/available-columns", response_model=AvailableColumnsResponse)
async def available_columns(
    entity_type: str = Query(pattern="^(quote|opportunity|customer|email)$"),
    current_user: User = Depends(get_current_user),
):
    """Get available columns for an entity type."""
    _check_feature_flag()

    if entity_type not in ALLOWED_COLUMNS:
        raise BadRequestException(f"Gecersiz varlik tipi: {entity_type}")

    join_columns = []
    for join_entity, join_cfg in ENTITY_JOINS.get(entity_type, {}).items():
        for col in join_cfg["columns"]:
            join_columns.append(f"{join_entity}.{col}")

    return {
        "data": {
            "entity_type": entity_type,
            "columns": ALLOWED_COLUMNS[entity_type],
            "join_columns": join_columns,
        }
    }


class ScheduleRequest(BaseModel):
    email_schedule: str | None = None  # weekly, daily, monthly, or None to disable
    email_recipients: list[str] | None = None


@router.patch("/templates/{template_id}/schedule", response_model=ScheduleResponse)
async def schedule_report(
    template_id: int,
    data: ScheduleRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Set up scheduled email delivery for a report template."""
    _check_feature_flag()

    template = await _get_user_template(db, template_id, current_user)

    if data.email_schedule and data.email_schedule not in ("daily", "weekly", "monthly"):
        raise BadRequestException("Gecersiz zamanlama: daily, weekly veya monthly olmali")

    import json
    template.email_schedule = data.email_schedule
    template.email_recipients = json.dumps(data.email_recipients) if data.email_recipients else None
    await db.flush()

    return {
        "data": {
            "id": template.id,
            "name": template.name,
            "email_schedule": template.email_schedule,
            "email_recipients": data.email_recipients,
        }
    }


# ── Helpers ──


async def _get_user_template(
    db: AsyncSession, template_id: int, current_user: User
) -> ReportTemplate:
    """Get a template, verifying tenant + ownership or manager role.

    Round-4 R4-TEN-14 — manager bypass would otherwise let a tenant-A
    manager update or execute a tenant-B template. Tenant guard runs
    first so cross-tenant probes return 404, indistinguishable from
    "doesn't exist".
    """
    from app.services.tenant_context import assert_same_tenant

    result = await db.execute(
        select(ReportTemplate).where(ReportTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException("Rapor sablonu bulunamadi")
    assert_same_tenant(template, current_user, exception_cls=NotFoundException)

    is_owner = template.created_by == current_user.id
    is_manager = current_user.role == "sales_manager"

    if not is_owner and not is_manager:
        raise ForbiddenException("Bu sablona erisim yetkiniz yok")

    return template


def _validate_columns_json(entity_type: str, columns_json: str) -> None:
    """Validate that columns_json is valid JSON with allowed column names."""
    try:
        columns = json.loads(columns_json)
    except json.JSONDecodeError:
        raise BadRequestException("columns_json gecerli bir JSON dizisi olmali")

    if not isinstance(columns, list) or not columns:
        raise BadRequestException("columns_json bos olmayan bir liste olmali")

    allowed = ALLOWED_COLUMNS.get(entity_type, [])
    # Accept dotted join columns (e.g. "customer.name") — validated at execution time
    plain_columns = [col for col in columns if "." not in col]
    invalid = [col for col in plain_columns if col not in allowed]
    if invalid:
        raise BadRequestException(
            f"Gecersiz sutunlar: {', '.join(invalid)}. "
            f"Izin verilen: {', '.join(allowed)}"
        )


def _validate_filters_json(filters_json: str) -> None:
    """Validate that filters_json is valid JSON array of filter objects."""
    try:
        filters = json.loads(filters_json)
    except json.JSONDecodeError:
        raise BadRequestException("filters_json gecerli bir JSON dizisi olmali")

    if not isinstance(filters, list):
        raise BadRequestException("filters_json bir liste olmali")

    for f in filters:
        if not isinstance(f, dict):
            raise BadRequestException("Her filtre bir nesne olmali")
        if "field" not in f or "operator" not in f:
            raise BadRequestException("Her filtre 'field' ve 'operator' alanlari icermeli")
