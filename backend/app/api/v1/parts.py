import io
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.spare_part import SparePart
from app.models.user import User

router = APIRouter(prefix="/parts", tags=["Spare Parts"])


@router.get("/")
async def list_parts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
        search_term = f"%{search}%"
        conditions.append(
            or_(
                SparePart.honeywell_code.ilike(search_term),
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


@router.get("/categories")
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List distinct part categories."""
    result = await db.execute(
        select(SparePart.category)
        .where(SparePart.is_active.is_(True))
        .where(SparePart.category.isnot(None))
        .distinct()
        .order_by(SparePart.category)
    )
    categories = [row[0] for row in result.all()]
    return categories


@router.get("/{part_id}")
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
        raise NotFoundException(f"Part with id {part_id} not found")

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


@router.post("/", status_code=201)
async def create_part(
    data: dict,
    current_user: User = Depends(require_role(UserRole.OPERATIONS)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new spare part (operations only)."""
    honeywell_code = data.get("honeywell_code")
    if not honeywell_code:
        raise BadRequestException("honeywell_code is required")

    # Check for duplicate
    existing = await db.execute(
        select(SparePart).where(SparePart.honeywell_code == honeywell_code)
    )
    if existing.scalar_one_or_none():
        raise BadRequestException(f"Part with code '{honeywell_code}' already exists")

    part = SparePart(
        honeywell_code=honeywell_code,
        name_en=data.get("name_en"),
        name_tr=data.get("name_tr"),
        description_en=data.get("description_en"),
        description_tr=data.get("description_tr"),
        category=data.get("category"),
        subcategory=data.get("subcategory"),
        keywords_json=data.get("keywords_json"),
        aliases_json=data.get("aliases_json"),
    )
    db.add(part)
    await db.flush()
    await db.refresh(part)

    return _part_to_dict(part)


@router.put("/{part_id}")
async def update_part(
    part_id: int,
    data: dict,
    current_user: User = Depends(require_role(UserRole.OPERATIONS)),
    db: AsyncSession = Depends(get_db),
):
    """Update a spare part (operations only)."""
    result = await db.execute(
        select(SparePart).where(SparePart.id == part_id)
    )
    part = result.scalar_one_or_none()
    if not part:
        raise NotFoundException(f"Part with id {part_id} not found")

    updatable_fields = [
        "honeywell_code", "name_en", "name_tr", "description_en",
        "description_tr", "category", "subcategory", "keywords_json", "aliases_json",
    ]
    for field in updatable_fields:
        if field in data:
            setattr(part, field, data[field])

    await db.flush()
    await db.refresh(part)

    return _part_to_dict(part)


@router.delete("/{part_id}", status_code=200)
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
        raise NotFoundException(f"Part with id {part_id} not found")

    part.is_active = False
    await db.flush()

    return {"message": f"Part {part_id} deactivated"}


@router.post("/import", status_code=201)
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
        raise BadRequestException("No file provided")

    safe_name = sanitize_filename(file.filename)
    suffix = os.path.splitext(safe_name)[1].lower()

    if suffix not in cfg.allowed_extensions:
        raise BadRequestException(f"Only {', '.join(cfg.allowed_extensions)} files are supported")

    content = await file.read()

    # Size check
    if len(content) > cfg.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise BadRequestException(f"File too large (max {cfg.MAX_UPLOAD_SIZE_MB} MB)")

    # Validate file content (magic bytes)
    content_start = content[:4]
    if suffix in ('.xlsx', '.xls'):
        # XLSX starts with PK (zip), XLS starts with D0 CF
        if not (content_start[:2] == b'PK' or content_start[:2] == b'\xd0\xcf'):
            raise BadRequestException("File content does not match extension")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from app.services.import_service import import_catalog_from_file
        result = await import_catalog_from_file(db, tmp_path)
    finally:
        os.unlink(tmp_path)

    return result


def _part_to_dict(part: SparePart) -> dict:
    """Convert SparePart to a dictionary response."""
    return {
        "id": part.id,
        "honeywell_code": part.honeywell_code,
        "name_en": part.name_en,
        "name_tr": part.name_tr,
        "description_en": part.description_en,
        "description_tr": part.description_tr,
        "category": part.category,
        "subcategory": part.subcategory,
        "keywords_json": part.keywords_json,
        "aliases_json": part.aliases_json,
        "is_active": part.is_active,
        "created_at": part.created_at.isoformat() if part.created_at else None,
    }
