import io
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import enforce_upload_rate_limit
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.spare_part import SparePart
from app.models.user import User
from app.schemas.spare_part import SparePartCreate, SparePartResponse, SparePartUpdate
from app.schemas.common import MessageResponse, PaginatedResponse

router = APIRouter(prefix="/parts", tags=["Spare Parts"])


@router.get("/", response_model=PaginatedResponse[SparePartResponse])
async def list_parts(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, description="Search by code or name"),
    category: str | None = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List spare parts with pagination and search."""
    query = select(SparePart).where(SparePart.is_active.is_(True))
    count_query = select(func.count(SparePart.id)).where(SparePart.is_active.is_(True))

    conditions = []
    if search:
        safe_search = search.replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{safe_search}%"
        conditions.append(
            or_(
                SparePart.honeywell_code.ilike(search_term),
                SparePart.model_number.ilike(search_term),
                SparePart.name_en.ilike(search_term),
                SparePart.name_tr.ilike(search_term),
            )
        )
    if category:
        conditions.append(SparePart.category == category)

    if conditions:
        combined = and_(*conditions)
        query = query.where(combined)
        count_query = count_query.where(combined)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(SparePart.honeywell_code).offset(offset).limit(page_size)

    result = await db.execute(query)
    parts = result.scalars().all()

    return {
        "items": [_part_to_dict(p) for p in parts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/categories", response_model=dict)
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List distinct part categories.

    Round-5 Phase 7 — wrapped in canonical envelope so SPA list
    consumers don't need a parts-specific shape. Total count is the
    distinct-category count (no real pagination needed since the
    cardinality is bounded by the catalog's category vocabulary).
    """
    result = await db.execute(
        select(SparePart.category)
        .where(SparePart.is_active.is_(True))
        .where(SparePart.category.isnot(None))
        .distinct()
        .order_by(SparePart.category)
    )
    categories = [row[0] for row in result.all()]
    return {"items": categories, "total": len(categories)}


@router.get("/{part_id}", response_model=dict)
async def get_part(
    part_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get part detail with prices."""
    result = await db.execute(
        select(SparePart).where(SparePart.id == part_id)
    )
    part = result.scalar_one_or_none()
    if not part:
        raise NotFoundException("Parca bulunamadi")

    data = _part_to_dict(part)
    data["prices"] = [
        {
            "id": p.id,
            "list_price": p.list_price,
            "discount_pct": p.discount_pct,
            "net_price": p.net_price,
            "currency": p.currency,
            "valid_from": p.valid_from.isoformat() if p.valid_from else None,
            "valid_until": p.valid_until.isoformat() if p.valid_until else None,
            "price_list_version": p.price_list_version,
        }
        for p in (part.prices or [])
    ]
    return data


@router.post("/", status_code=201, response_model=dict)
async def create_part(
    data: SparePartCreate,
    current_user: User = Depends(require_role(UserRole.OPERATIONS)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new spare part (operations only). Validated via Pydantic schema."""
    # Check for duplicate
    existing = await db.execute(
        select(SparePart).where(SparePart.honeywell_code == data.honeywell_code)
    )
    if existing.scalar_one_or_none():
        raise BadRequestException(f"'{data.honeywell_code}' kodlu parca zaten mevcut")

    part = SparePart(**data.model_dump())
    db.add(part)
    await db.flush()
    await db.refresh(part)

    return _part_to_dict(part)


@router.put("/{part_id}", response_model=dict)
async def update_part(
    part_id: int,
    data: SparePartUpdate,
    current_user: User = Depends(require_role(UserRole.OPERATIONS)),
    db: AsyncSession = Depends(get_db),
):
    """Update a spare part (operations only). Validated via Pydantic schema."""
    result = await db.execute(
        select(SparePart).where(SparePart.id == part_id)
    )
    part = result.scalar_one_or_none()
    if not part:
        raise NotFoundException("Parca bulunamadi")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(part, field, value)

    await db.flush()
    await db.refresh(part)

    return _part_to_dict(part)


@router.delete("/{part_id}", status_code=200, response_model=MessageResponse)
async def delete_part(
    part_id: int,
    current_user: User = Depends(require_role(UserRole.OPERATIONS)),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a spare part (set is_active=False)."""
    result = await db.execute(
        select(SparePart).where(SparePart.id == part_id)
    )
    part = result.scalar_one_or_none()
    if not part:
        raise NotFoundException("Parca bulunamadi")

    part.is_active = False
    await db.flush()

    return {"message": f"Part {part_id} deactivated"}


@router.post(
    "/import",
    status_code=201,
    dependencies=[Depends(enforce_upload_rate_limit)],
    response_model=dict,
)
async def import_catalog(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.OPERATIONS, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Import parts + prices from a single Excel/CSV file.

    Each row can contain both part info and price info.
    Required column: honeywell_code
    Part columns: name_en, name_tr, category, subcategory, description_en, description_tr
    Price columns: list_price, discount_pct, net_price, currency, valid_from, valid_until
    """
    import tempfile
    import os

    from app.core.config import settings as cfg
    from app.core.security import sanitize_filename

    if not file.filename:
        raise BadRequestException("Dosya saglanmadi")

    safe_name = sanitize_filename(file.filename)
    suffix = os.path.splitext(safe_name)[1].lower()

    allowed = list(cfg.allowed_extensions) + [".json", ".pdf"]
    if suffix not in allowed:
        raise BadRequestException(f"Only {', '.join(allowed)} files are supported")

    from app.core.upload_utils import read_upload_file_limited
    content = await read_upload_file_limited(file, max_bytes=cfg.MAX_UPLOAD_SIZE_MB * 1024 * 1024)

    # Validate file content (magic bytes)
    content_start = content[:4]
    if suffix in ('.xlsx', '.xls'):
        if not (content_start[:2] == b'PK' or content_start[:2] == b'\xd0\xcf'):
            raise BadRequestException("File content does not match extension")
    elif suffix == '.json':
        if content_start[:1] not in (b'{', b'[', b'\xef'):
            raise BadRequestException("File content does not look like JSON")
    elif suffix == '.pdf':
        if content_start[:4] != b'%PDF':
            raise BadRequestException("File content does not look like PDF")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix == '.pdf':
            # PDF import: extract parts table from PDF
            from app.services.pdf_import_service import extract_parts_from_pdf
            from app.models.spare_part import SparePart
            from sqlalchemy import select as sa_select

            pdf_parts = extract_parts_from_pdf(tmp_path)
            created = 0
            updated = 0
            for p in pdf_parts:
                code = p.get("honeywell_code", "").strip()
                if not code:
                    continue
                existing = await db.execute(
                    sa_select(SparePart).where(SparePart.honeywell_code == code)
                )
                part = existing.scalar_one_or_none()
                if part:
                    if p.get("description"):
                        part.name_en = p["description"]
                    if p.get("unit_price"):
                        part.supplier_price = p["unit_price"]
                    updated += 1
                else:
                    new_part = SparePart(
                        honeywell_code=code,
                        name_en=p.get("description", ""),
                        name_tr=p.get("description", ""),
                        description_en=p.get("description", ""),
                        description_tr=p.get("description", ""),
                        supplier_price=p.get("unit_price"),
                        is_active=True,
                    )
                    db.add(new_part)
                    created += 1

            await db.flush()
            result = {
                "parts_created": created,
                "parts_updated": updated,
                "source": "pdf",
                "total_extracted": len(pdf_parts),
            }
        else:
            from app.services.product_import_pipeline import import_products_from_file
            result = await import_products_from_file(db, tmp_path)
    finally:
        os.unlink(tmp_path)

    return result


def _part_to_dict(part: SparePart) -> dict:
    """Convert SparePart to a dictionary response.

    R5-API-7 — ``min_margin_pct`` is consumed by the pricing engine as
    a guardrail but was previously hidden from every consumer. Surface
    it so part editors can show + edit the threshold instead of
    operators having to make direct DB edits.
    """
    return {
        "id": part.id,
        "honeywell_code": part.honeywell_code,
        "model_number": part.model_number,
        "info": part.info,
        "name_en": part.name_en,
        "name_tr": part.name_tr,
        "description_en": part.description_en,
        "description_tr": part.description_tr,
        "category": part.category,
        "subcategory": part.subcategory,
        "transfer_price": part.transfer_price,
        "supplier_price": part.supplier_price,
        "price_currency": part.price_currency,
        "min_margin_pct": getattr(part, "min_margin_pct", None),
        "keywords_json": part.keywords_json,
        "aliases_json": part.aliases_json,
        "is_active": part.is_active,
        "created_at": part.created_at.isoformat() if part.created_at else None,
    }
