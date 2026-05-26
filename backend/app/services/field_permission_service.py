from __future__ import annotations

import logging
import re
from contextvars import ContextVar

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.field_permission import FieldPermission

logger = logging.getLogger(__name__)

VALID_ACCESS_LEVELS = {"read", "write", "hidden", "masked"}
# Round-4 R4-PERM-3 widened to include the entities that hold PII the
# admin UI must be able to mask (signer email on contract, billing
# address on invoice, etc).
VALID_ENTITY_TYPES = {
    "customer",
    "quote",
    "opportunity",
    "email",
    "lead",
    "contract",
    "invoice",
    "subscription",
    "campaign",
}
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


# ─────────────────────── request-scoped helpers ──────────────────────
#
# Round-4 R4-PERM-1 fix: ``apply_to_response`` was previously dead code
# (zero call sites outside the admin CRUD). The helpers below let the
# serializer functions (``_opp_to_dict`` / ``_customer_to_dict`` /
# ``_lead_to_dict`` / ``_quote_to_dict``) apply masking with a single
# synchronous call, after the route handler pre-loads permissions for
# the current user's role.
#
# Pre-loading is intentional: the field_permission table is keyed on
# (role, entity_type, field_name), so for one role we can load the
# entire ruleset in a single async query and reuse it for every row in
# a list response without re-hitting Redis/DB.


async def load_field_perms_for_role(
    db: AsyncSession,
    role: str,
    entity_types: tuple[str, ...] = tuple(VALID_ENTITY_TYPES),
) -> dict[str, dict[str, str]]:
    """Pre-fetch all field-permission rules for a role.

    Returns ``{entity_type: {field_name: access_level}}``. Empty dicts
    for entities with no configured rules (so callers can do
    ``perms.get(entity_type, {})`` without branching).

    Single-query: filters by role + entity_types, then groups in
    Python. Cheaper than N round-trips when a route response embeds
    multiple entity types.
    """
    if not role or role not in VALID_ROLES:
        return {entity_type: {} for entity_type in entity_types}
    result = await db.execute(
        select(FieldPermission).where(
            FieldPermission.role == role,
            FieldPermission.entity_type.in_(entity_types),
        )
    )
    grouped: dict[str, dict[str, str]] = {entity_type: {} for entity_type in entity_types}
    for row in result.scalars().all():
        grouped.setdefault(row.entity_type, {})[row.field_name] = row.access_level
    return grouped


def apply_perms_sync(
    data: dict,
    permissions: dict[str, str] | None,
) -> dict:
    """Apply hidden / masked rules to a dict using pre-loaded permissions.

    No-ops when ``permissions`` is empty so unconfigured entities are
    untouched. Pure function — safe to call from sync serializers.
    """
    if not permissions or not data:
        return data
    filtered: dict = {}
    for key, value in data.items():
        access = permissions.get(key)
        if access == "hidden":
            continue
        if access == "masked" and value is not None:
            filtered[key] = FieldPermissionService.mask_value(str(value), key)
        else:
            filtered[key] = value
    return filtered


# ContextVar set per request by ``prefetch_field_perms_dependency`` so
# sync serializers can apply masking without taking new arguments.
# Falls back to an empty dict outside a request scope (tests, jobs).
_FIELD_PERMS_CV: ContextVar[dict[str, dict[str, str]]] = ContextVar(
    "field_perms_cv", default={}
)


def get_request_field_perms(entity_type: str) -> dict[str, str]:
    """Return the masking ruleset for ``entity_type`` in the current request."""
    return _FIELD_PERMS_CV.get().get(entity_type, {})


def apply_request_perms(data: dict, entity_type: str) -> dict:
    """Apply request-scoped masking to a serializer's output dict."""
    return apply_perms_sync(data, get_request_field_perms(entity_type))


# D-018 — auditable masking decorator. Endpoints returning data for
# one of the 9 maskable entity types should wrap with this. Two
# benefits over manually calling ``apply_request_perms`` at the end
# of each handler:
#
#   1. The masking is visibly bound to the endpoint surface (lint
#      can grep the decorator).
#   2. It handles both single-object and ``items=[...]`` envelope
#      shapes uniformly, so list endpoints don't accidentally skip
#      the per-row mask.
def apply_request_perms_to_response(entity_type: str):
    """Wrap an endpoint so its return value is masked per role.

    Usage::

        @router.get("/{cid}", response_model=CustomerOut)
        @apply_request_perms_to_response("customer")
        async def get_customer(...):
            ...

    The decorator is permissive: when the return value is not a dict
    and is not a list-of-dicts (e.g. a Pydantic model that the
    response_model machinery hasn't dumped yet), the decorator is a
    no-op and the FastAPI ``response_model`` masking can run via the
    Pydantic-aware path. This is intentional — the decorator covers
    the common "raw dict" return idiom without breaking the modern
    typed-response path.
    """

    from functools import wraps

    def deco(fn):
        @wraps(fn)
        async def wrap(*args, **kwargs):
            result = await fn(*args, **kwargs)
            if isinstance(result, dict):
                # Common shapes: {"items": [...]} or a single record.
                if "items" in result and isinstance(result["items"], list):
                    result = {
                        **result,
                        "items": [
                            apply_request_perms(item, entity_type)
                            if isinstance(item, dict)
                            else item
                            for item in result["items"]
                        ],
                    }
                else:
                    result = apply_request_perms(result, entity_type)
            elif isinstance(result, list):
                result = [
                    apply_request_perms(item, entity_type)
                    if isinstance(item, dict)
                    else item
                    for item in result
                ]
            return result

        # Tag the wrapper so the lint test can find it.
        wrap.__field_perms_entity__ = entity_type  # type: ignore[attr-defined]
        return wrap

    return deco


async def prefetch_field_perms_dependency(
    db: AsyncSession,
    role: str | None,
) -> None:
    """Pre-load all field permissions for ``role`` into the request CV.

    Called from a FastAPI dependency at the route layer. Best-effort —
    a DB hiccup leaves the CV empty (no masking) rather than failing
    the request, since the rules are KVKK *masking* not auth: the
    fail-closed alternative would block reads instead of just exposing
    an unmasked value.
    """
    if not role:
        _FIELD_PERMS_CV.set({})
        return
    try:
        perms = await load_field_perms_for_role(db, role)
    except Exception:
        logger.exception("field_permission preload failed; serving unmasked")
        perms = {}
    _FIELD_PERMS_CV.set(perms)
