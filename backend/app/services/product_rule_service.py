"""Product rule engine — evaluates catalog rules for quote items."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.product_rule import ProductRule

logger = logging.getLogger(__name__)


class ProductRuleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate_for_item(
        self,
        spare_part_id: int | None,
        category: str | None,
        quantity: int,
        unit_price: float,
    ) -> list[dict]:
        """Evaluate all active rules for an item. Returns list of {rule_type, action}."""
        query = (
            select(ProductRule)
            .where(ProductRule.is_active.is_(True))
            .order_by(ProductRule.priority.desc())
        )
        result = await self.db.execute(query)
        rules = result.scalars().all()

        matched_actions: list[dict] = []

        for rule in rules:
            if not self._rule_applies_to_item(rule, spare_part_id, category):
                continue
            if not self._condition_matches(rule, quantity, unit_price):
                continue

            try:
                action = json.loads(rule.action_json)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Gecersiz action_json, rule_id=%d", rule.id)
                continue

            matched_actions.append({
                "rule_id": rule.id,
                "rule_type": rule.rule_type,
                "action": action,
            })

        return matched_actions

    async def apply_rules(self, quote_items: list[dict]) -> list[dict]:
        """Apply rules to all items in a quote. Returns modifications list.

        Each item dict should have: spare_part_id, category, quantity, unit_price.
        """
        modifications: list[dict] = []

        for idx, item in enumerate(quote_items):
            actions = await self.evaluate_for_item(
                spare_part_id=item.get("spare_part_id"),
                category=item.get("category"),
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price", 0.0),
            )
            for action_info in actions:
                modifications.append({
                    "item_index": idx,
                    "spare_part_id": item.get("spare_part_id"),
                    **action_info,
                })

        return modifications

    async def create_rule(
        self,
        *,
        rule_type: str,
        condition_json: str,
        action_json: str,
        spare_part_id: int | None = None,
        category: str | None = None,
        priority: int = 0,
        is_active: bool = True,
    ) -> ProductRule:
        """Create a new product rule."""
        valid_types = {"volume_discount", "bundle_suggest", "min_quantity", "max_discount"}
        if rule_type not in valid_types:
            raise BadRequestException(
                f"Gecersiz rule_type: {rule_type}. Gecerli degerler: {', '.join(sorted(valid_types))}"
            )

        # Validate JSON strings
        for label, value in [("condition_json", condition_json), ("action_json", action_json)]:
            try:
                json.loads(value)
            except (json.JSONDecodeError, TypeError):
                raise BadRequestException(f"Gecersiz JSON formatı: {label}")

        rule = ProductRule(
            spare_part_id=spare_part_id,
            category=category,
            rule_type=rule_type,
            condition_json=condition_json,
            action_json=action_json,
            priority=priority,
            is_active=is_active,
        )
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def list_rules(self) -> list[ProductRule]:
        """List all product rules ordered by priority."""
        result = await self.db.execute(
            select(ProductRule).order_by(ProductRule.priority.desc(), ProductRule.id)
        )
        return list(result.scalars().all())

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete a product rule by ID."""
        result = await self.db.execute(
            select(ProductRule).where(ProductRule.id == rule_id)
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise NotFoundException("Urun kurali bulunamadi")

        await self.db.delete(rule)
        await self.db.flush()
        return True

    # ── Private helpers ──

    def _rule_applies_to_item(
        self,
        rule: ProductRule,
        spare_part_id: int | None,
        category: str | None,
    ) -> bool:
        """Check if a rule targets this item (by spare_part_id or category)."""
        # Rule with no spare_part_id and no category applies to all items
        if rule.spare_part_id is None and rule.category is None:
            return True
        if rule.spare_part_id is not None and rule.spare_part_id == spare_part_id:
            return True
        if rule.category is not None and category and rule.category.lower() == category.lower():
            return True
        return False

    def _condition_matches(
        self,
        rule: ProductRule,
        quantity: int,
        unit_price: float,
    ) -> bool:
        """Evaluate the rule's condition_json against item values."""
        try:
            condition = json.loads(rule.condition_json)
        except (json.JSONDecodeError, TypeError):
            return False

        field = condition.get("field", "")
        op = condition.get("op", "")
        value = condition.get("value", 0)

        field_map = {
            "quantity": quantity,
            "unit_price": unit_price,
        }
        actual = field_map.get(field)
        if actual is None:
            return False

        try:
            value = float(value)
        except (ValueError, TypeError):
            return False

        op_map = {
            "gte": actual >= value,
            "gt": actual > value,
            "lte": actual <= value,
            "lt": actual < value,
            "eq": actual == value,
            "neq": actual != value,
        }
        return op_map.get(op, False)
