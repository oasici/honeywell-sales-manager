"""Access control service -- team membership + sharing rules."""
from __future__ import annotations

import json
import logging

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.core.redis_client import get_redis
from app.models.team import AccountTeam, SharingRule

logger = logging.getLogger(__name__)

# Maps entity types to their model and the field that links to customer
ENTITY_CUSTOMER_FK = {
    "customer": ("id", None),
    "opportunity": ("customer_id", Opportunity),
    "quote": ("customer_id", Quote),
}


class AccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def can_access(
        self,
        user_id: int,
        user_role: str,
        entity_type: str,
        entity_id: int,
        owner_id: int | None = None,
    ) -> bool:
        """Check if user can access entity.

        Order:
        1) Manager -> full access
        2) Owner -> yes
        3) AccountTeam member -> yes
        4) SharingRule match -> yes
        """
        if user_role == "sales_manager":
            return True

        if owner_id and owner_id == user_id:
            return True

        customer_id = await self._resolve_customer_id(entity_type, entity_id)
        if customer_id is not None:
            has_team = await self._check_team_membership(user_id, customer_id)
            if has_team:
                return True

        has_rule = await self._check_sharing_rules(user_id, user_role, entity_type, entity_id)
        if has_rule:
            return True

        return False

    async def get_accessible_customer_ids(
        self,
        user_id: int,
        user_role: str,
    ) -> list[int] | None:
        """Return list of customer IDs user can access, or None for managers (all)."""
        if user_role == "sales_manager":
            return None

        cache_key = f"access:customers:{user_id}"
        redis = get_redis()

        # Check Redis cache first
        if redis is not None:
            try:
                cached_value = await redis.get(cache_key)
                if cached_value is not None:
                    return json.loads(cached_value)
            except Exception:
                logger.warning("Redis read failed for key=%s, falling back to DB", cache_key)

        customer_ids: set[int] = set()

        # Own customers (created_by)
        stmt = select(Customer.id).where(Customer.created_by == user_id)
        result = await self.db.execute(stmt)
        customer_ids.update(row[0] for row in result.all())

        # Team memberships
        stmt = select(AccountTeam.customer_id).where(AccountTeam.user_id == user_id)
        result = await self.db.execute(stmt)
        customer_ids.update(row[0] for row in result.all())

        result_list = list(customer_ids)

        # Cache the result in Redis
        if redis is not None:
            try:
                await redis.setex(cache_key, 60, json.dumps(result_list))
            except Exception:
                logger.warning("Redis write failed for key=%s", cache_key)

        return result_list

    async def add_team_member(
        self,
        customer_id: int,
        user_id: int,
        role: str = "member",
    ) -> AccountTeam:
        """Add a user to a customer's account team."""
        member = AccountTeam(
            customer_id=customer_id,
            user_id=user_id,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        await self.invalidate_access_cache(user_id)
        return member

    async def remove_team_member(self, customer_id: int, user_id: int) -> None:
        """Remove a user from a customer's account team."""
        stmt = select(AccountTeam).where(
            and_(
                AccountTeam.customer_id == customer_id,
                AccountTeam.user_id == user_id,
            )
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            await self.db.delete(member)
            await self.db.flush()
            await self.invalidate_access_cache(user_id)

    async def invalidate_access_cache(self, user_id: int) -> None:
        """Clear cached access for a user."""
        redis = get_redis()
        if redis is not None:
            try:
                await redis.delete(f"access:customers:{user_id}")
            except Exception:
                logger.warning("Redis invalidation failed for user_id=%s", user_id)

    async def invalidate_all_access_cache(self) -> None:
        """Clear all access caches (after sharing rule change)."""
        redis = get_redis()
        if redis is not None:
            try:
                cursor = "0"
                while cursor:
                    cursor, keys = await redis.scan(
                        cursor=cursor, match="access:customers:*", count=100
                    )
                    if keys:
                        await redis.delete(*keys)
            except Exception:
                logger.warning("Redis bulk invalidation failed for access caches")

    async def get_team_members(self, customer_id: int) -> list[AccountTeam]:
        """Get all team members for a customer."""
        stmt = select(AccountTeam).where(AccountTeam.customer_id == customer_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _resolve_customer_id(
        self, entity_type: str, entity_id: int
    ) -> int | None:
        """Resolve the customer_id for a given entity."""
        if entity_type == "customer":
            return entity_id

        mapping = ENTITY_CUSTOMER_FK.get(entity_type)
        if mapping is None:
            return None

        fk_field, model = mapping
        if model is None:
            return None

        stmt = select(getattr(model, fk_field)).where(model.id == entity_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _check_team_membership(self, user_id: int, customer_id: int) -> bool:
        """Check if user is a member of the customer's account team."""
        stmt = select(AccountTeam.id).where(
            and_(
                AccountTeam.customer_id == customer_id,
                AccountTeam.user_id == user_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _check_sharing_rules(
        self,
        user_id: int,
        user_role: str,
        entity_type: str,
        entity_id: int,
    ) -> bool:
        """Check if any active sharing rule grants access."""
        stmt = select(SharingRule).where(
            and_(
                SharingRule.entity_type == entity_type,
                SharingRule.is_active.is_(True),
            )
        )
        result = await self.db.execute(stmt)
        rules = result.scalars().all()

        for rule in rules:
            is_target = self._is_rule_target(rule, user_id, user_role)
            if not is_target:
                continue

            matches = await self._evaluate_rule_criteria(rule, entity_type, entity_id)
            if matches:
                return True

        return False

    def _is_rule_target(self, rule: SharingRule, user_id: int, user_role: str) -> bool:
        """Check if the user matches the sharing rule's target."""
        if rule.share_with_user_id and rule.share_with_user_id == user_id:
            return True
        if rule.share_with_role and rule.share_with_role == user_role:
            return True
        return False

    async def _evaluate_rule_criteria(
        self,
        rule: SharingRule,
        entity_type: str,
        entity_id: int,
    ) -> bool:
        """Evaluate rule criteria against the entity."""
        try:
            criteria = json.loads(rule.criteria_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Gecersiz kural kriterleri: rule_id=%s", rule.id)
            return False

        field_name = criteria.get("field")
        operator = criteria.get("operator")
        value = criteria.get("value")

        if not all([field_name, operator]):
            return False

        model_map = {
            "customer": Customer,
            "opportunity": Opportunity,
            "quote": Quote,
        }
        model = model_map.get(entity_type)
        if model is None:
            return False

        column = getattr(model, field_name, None)
        if column is None:
            return False

        stmt = select(model.id).where(model.id == entity_id)

        if operator == "eq":
            stmt = stmt.where(column == value)
        elif operator == "neq":
            stmt = stmt.where(column != value)
        elif operator == "contains":
            stmt = stmt.where(column.ilike(f"%{value}%"))
        elif operator == "gt":
            stmt = stmt.where(column > value)
        elif operator == "lt":
            stmt = stmt.where(column < value)
        else:
            return False

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
