import math

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])

VALID_ROLES = {role.value for role in UserRole}


class RoleUpdate(BaseModel):
    role: str


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
        raise NotFoundException(f"{user_id} numarali kullanici bulunamadi")

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
        raise NotFoundException(f"{user_id} numarali kullanici bulunamadi")

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
