from __future__ import annotations

import csv
import io
import math

from fastapi import APIRouter, Depends, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.rate_limit import enforce_upload_rate_limit
from app.core.security import hash_password, validate_password_strength
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])

VALID_ROLES = {role.value for role in UserRole}


class RoleUpdate(BaseModel):
    role: str


class PasswordResetRequest(BaseModel):
    new_password: str


@router.get("/")
async def list_users(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination (sales_manager only)."""
    count_query = select(func.count(User.id))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    main_query = (
        select(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(main_query)
    users = result.scalars().all()

    return {
        "items": [_user_to_dict(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.patch("/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Activate or deactivate a user (sales_manager only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("Kullanici bulunamadi")

    if user.id == current_user.id:
        raise BadRequestException("Kendi hesabinizi deaktif edemezsiniz")

    # Prevent deactivating the last active manager
    if user.is_active and user.role == UserRole.SALES_MANAGER.value:
        manager_count = await db.execute(
            select(func.count(User.id)).where(
                User.role == UserRole.SALES_MANAGER.value,
                User.is_active.is_(True),
                User.id != user_id,
            )
        )
        if (manager_count.scalar() or 0) == 0:
            raise BadRequestException("Son aktif yonetici deaktif edilemez")

    user.is_active = not user.is_active
    await db.flush()
    await db.refresh(user)

    return _user_to_dict(user)


@router.patch("/{user_id}/role")
async def change_user_role(
    user_id: int,
    data: RoleUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's role (sales_manager only)."""
    if data.role not in VALID_ROLES:
        raise BadRequestException(
            f"Gecersiz rol: '{data.role}'. Gecerli roller: {', '.join(sorted(VALID_ROLES))}"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("Kullanici bulunamadi")

    if user.id == current_user.id:
        raise BadRequestException("Kendi rolunuzu degistiremezsiniz")

    # Prevent demoting the last manager
    if user.role == UserRole.SALES_MANAGER.value and data.role != UserRole.SALES_MANAGER.value:
        manager_count = await db.execute(
            select(func.count(User.id)).where(
                User.role == UserRole.SALES_MANAGER.value,
                User.is_active.is_(True),
                User.id != user_id,
            )
        )
        if (manager_count.scalar() or 0) == 0:
            raise BadRequestException("Son yonetici rolu degistirilemez")

    user.role = data.role
    await db.flush()
    await db.refresh(user)

    return _user_to_dict(user)


@router.patch("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    data: PasswordResetRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Admin reset another user's password. Manager only."""
    pw_error = validate_password_strength(data.new_password)
    if pw_error:
        raise BadRequestException(pw_error)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("Kullanici bulunamadi")

    user.hashed_password = hash_password(data.new_password)
    user.password_change_required = False
    await db.flush()

    return {"message": "Sifre sifirlandi", "user_id": user.id, "email": user.email}


@router.post(
    "/bulk-import",
    dependencies=[Depends(enforce_upload_rate_limit)],
)
async def bulk_import_users(
    file: UploadFile,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """CSV upload for batch user creation. Manager only.

    Expected CSV columns: email, full_name, role, password
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise BadRequestException("Sadece CSV dosyasi yuklenebilir")

    from app.core.config import settings as cfg
    from app.core.upload_utils import read_upload_file_limited
    content = await read_upload_file_limited(file, max_bytes=cfg.MAX_UPLOAD_SIZE_MB * 1024 * 1024)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise BadRequestException("Dosya UTF-8 formatinda olmali")

    reader = csv.DictReader(io.StringIO(text))
    required_columns = {"email", "full_name", "role", "password"}
    if not reader.fieldnames or not required_columns.issubset(set(reader.fieldnames)):
        raise BadRequestException(
            f"CSV dosyasinda su sutunlar olmali: {', '.join(sorted(required_columns))}"
        )

    from app.core.security import hash_password

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for row_num, row in enumerate(reader, start=2):
        email = (row.get("email") or "").strip().lower()
        full_name = (row.get("full_name") or "").strip()
        role = (row.get("role") or "").strip()
        password = (row.get("password") or "").strip()

        # Validate row
        if not email or "@" not in email:
            errors.append({"row": row_num, "email": email, "error": "Gecersiz email"})
            continue

        if not full_name:
            errors.append({"row": row_num, "email": email, "error": "Isim bos olamaz"})
            continue

        if role not in VALID_ROLES:
            errors.append({
                "row": row_num,
                "email": email,
                "error": f"Gecersiz rol: {role}",
            })
            continue

        if len(password) < 6:
            errors.append({
                "row": row_num,
                "email": email,
                "error": "Sifre en az 6 karakter olmali",
            })
            continue

        # Check for duplicate
        existing = await db.execute(select(User.id).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        user = User(
            email=email,
            full_name=full_name,
            role=role,
            hashed_password=hash_password(password),
            is_active=True,
        )
        db.add(user)
        imported += 1

    if imported > 0:
        await db.flush()

    return {
        "message": f"{imported} kullanici iceri aktarildi, {skipped} atlanildi",
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


def _user_to_dict(user: User) -> dict:
    """Convert User to a dictionary response (excludes sensitive fields)."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
