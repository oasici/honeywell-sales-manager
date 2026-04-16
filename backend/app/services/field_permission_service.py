from __future__ import annotations

import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.field_permission import FieldPermission

logger = logging.getLogger(__name__)

VALID_ACCESS_LEVELS = {"read", "write", "hidden", "masked"}
VALID_ENTITY_TYPES = {"customer", "quote", "opportunity", "email", "lead"}
VALID_ROLES = {"sales_rep", "sales_manager", "operations"}

CACHE_TTL_SECONDS = 300  # 5 minutes


class FieldPermissionService:
    """Manages field-level access control per role and entity type."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_permissions(self, role: str, entity_type: str) -> dict[str, str]:
        """Return {field_name: access_level} for this role+entity.

        Attempts Redis cache first (5 min TTL), falls back to DB.
        """
        cache_key = f"field_perm:{role}:{entity_type}"

        # Try Redis cache
        try:
            from app.core.redis_client import get_redis

            redis = get_redis()
            if redis is not None:
                import json

                cached = await redis.get(cache_key)
                if cached is not None:
                    return json.loads(cached)
        except Exception:
            pass

        # Fetch from DB
        result = await self.db.execute(
            select(FieldPermission).where(
                FieldPermission.role == role,
                FieldPermission.entity_type == entity_type,
            )
        )
        permissions = {row.field_name: row.access_level for row in result.scalars().all()}

        # Store in Redis cache
        try:
            from app.core.redis_client import get_redis

            redis = get_redis()
            if redis is not None:
                import json

                await redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(permissions))
        except Exception:
            pass

        return permissions

    async def apply_to_response(
        self,
        data: dict,
        role: str,
        entity_type: str,
    ) -> dict:
        """Strip hidden fields, mask masked fields from response dict."""
        permissions = await self.get_permissions(role, entity_type)
        if not permissions:
            return data

        filtered = {}
        for key, value in data.items():
            access = permissions.get(key)
            if access == "hidden":
                continue
            if access == "masked" and value is not None:
                filtered[key] = self.mask_value(str(value), key)
            else:
                filtered[key] = value
        return filtered

    @staticmethod
    def mask_value(value: str, field_name: str) -> str:
        """Mask sensitive values based on field name heuristics.

        email -> o***@domain.com
        phone -> +90 *** ** 00
        tax_id -> ***456
        default -> first char + *** + last two chars
        """
        if not value:
            return "***"

        field_lower = field_name.lower()

        if "email" in field_lower:
            match = re.match(r"^(.)(.*?)(@.+)$", value)
            if match:
                return f"{match.group(1)}***{match.group(3)}"
            return "***"

        if "phone" in field_lower or "tel" in field_lower:
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                return f"+{digits[:2]} *** ** {digits[-2:]}"
            return "*** ***"

        if "tax" in field_lower or "vergi" in field_lower:
            if len(value) >= 3:
                return f"***{value[-3:]}"
            return "***"

        # Default masking
        if len(value) >= 3:
            return f"{value[0]}***{value[-2:]}"
        return "***"

    async def set_permission(
        self,
        role: str,
        entity_type: str,
        field_name: str,
        access_level: str,
    ) -> FieldPermission:
        """Create or update a field permission."""
        if access_level not in VALID_ACCESS_LEVELS:
            raise ValueError(f"Gecersiz erisim seviyesi: {access_level}")
        if entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(f"Gecersiz varlik tipi: {entity_type}")
        if role not in VALID_ROLES:
            raise ValueError(f"Gecersiz rol: {role}")

        # Upsert: check existing
        result = await self.db.execute(
            select(FieldPermission).where(
                FieldPermission.role == role,
                FieldPermission.entity_type == entity_type,
                FieldPermission.field_name == field_name,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.access_level = access_level
            await self.db.flush()
            await self.db.refresh(existing)
            await self._invalidate_cache(role, entity_type)
            return existing

        permission = FieldPermission(
            role=role,
            entity_type=entity_type,
            field_name=field_name,
            access_level=access_level,
        )
        self.db.add(permission)
        await self.db.flush()
        await self.db.refresh(permission)
        await self._invalidate_cache(role, entity_type)
        return permission

    async def list_permissions(
        self,
        role: str | None = None,
        entity_type: str | None = None,
    ) -> list[FieldPermission]:
        """List permissions with optional filters."""
        stmt = select(FieldPermission)
        if role is not None:
            stmt = stmt.where(FieldPermission.role == role)
        if entity_type is not None:
            stmt = stmt.where(FieldPermission.entity_type == entity_type)
        stmt = stmt.order_by(FieldPermission.id)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_permission(self, permission_id: int) -> bool:
        """Delete a permission by ID. Returns True if deleted."""
        result = await self.db.execute(
            select(FieldPermission).where(FieldPermission.id == permission_id)
        )
        permission = result.scalar_one_or_none()
        if permission is None:
            return False

        role = permission.role
        entity_type = permission.entity_type
        await self.db.execute(
            delete(FieldPermission).where(FieldPermission.id == permission_id)
        )
        await self.db.flush()
        await self._invalidate_cache(role, entity_type)
        return True

    async def _invalidate_cache(self, role: str, entity_type: str) -> None:
        """Invalidate the Redis cache for a role+entity pair."""
        try:
            from app.core.redis_client import get_redis

            redis = get_redis()
            if redis is not None:
                await redis.delete(f"field_perm:{role}:{entity_type}")
        except Exception:
            pass
