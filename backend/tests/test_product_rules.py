"""Tests for product catalog rules — creation, evaluation, matching."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_rule import ProductRule
from app.services.product_rule_service import ProductRuleService


@pytest_asyncio.fixture
async def rule_service(db: AsyncSession) -> ProductRuleService:
    return ProductRuleService(db)


@pytest.mark.asyncio
async def test_create_rule(rule_service: ProductRuleService):
    """Rule creation with valid data should succeed."""
    rule = await rule_service.create_rule(
        rule_type="volume_discount",
        condition_json='{"field":"quantity","op":"gte","value":100}',
        action_json='{"type":"discount","value":5}',
        priority=10,
    )
    assert rule.id is not None
    assert rule.rule_type == "volume_discount"
    assert rule.priority == 10
    assert rule.is_active is True


@pytest.mark.asyncio
async def test_create_rule_invalid_type(rule_service: ProductRuleService):
    """Rule creation with invalid rule_type should raise."""
    from app.core.exceptions import BadRequestException

    with pytest.raises(BadRequestException, match="Gecersiz rule_type"):
        await rule_service.create_rule(
            rule_type="invalid_type",
            condition_json='{"field":"quantity","op":"gte","value":10}',
            action_json='{"type":"discount","value":5}',
        )


@pytest.mark.asyncio
async def test_create_rule_invalid_json(rule_service: ProductRuleService):
    """Rule creation with malformed JSON should raise."""
    from app.core.exceptions import BadRequestException

    with pytest.raises(BadRequestException, match="Gecersiz JSON"):
        await rule_service.create_rule(
            rule_type="volume_discount",
            condition_json="not-json",
            action_json='{"type":"discount","value":5}',
        )


@pytest.mark.asyncio
async def test_volume_discount_applies(rule_service: ProductRuleService):
    """Volume discount rule should match when quantity meets threshold."""
    await rule_service.create_rule(
        rule_type="volume_discount",
        condition_json='{"field":"quantity","op":"gte","value":50}',
        action_json='{"type":"discount","value":10}',
    )

    actions = await rule_service.evaluate_for_item(
        spare_part_id=None,
        category=None,
        quantity=100,
        unit_price=25.0,
    )
    assert len(actions) == 1
    assert actions[0]["rule_type"] == "volume_discount"
    assert actions[0]["action"]["value"] == 10


@pytest.mark.asyncio
async def test_non_matching_rule_skipped(rule_service: ProductRuleService):
    """Rule should not match when quantity is below threshold."""
    await rule_service.create_rule(
        rule_type="volume_discount",
        condition_json='{"field":"quantity","op":"gte","value":100}',
        action_json='{"type":"discount","value":5}',
    )

    actions = await rule_service.evaluate_for_item(
        spare_part_id=None,
        category=None,
        quantity=10,
        unit_price=25.0,
    )
    assert len(actions) == 0


@pytest.mark.asyncio
async def test_category_specific_rule(rule_service: ProductRuleService):
    """Rule targeting a specific category should only match items in that category."""
    await rule_service.create_rule(
        rule_type="min_quantity",
        category="sensors",
        condition_json='{"field":"quantity","op":"gte","value":1}',
        action_json='{"type":"min_qty","value":5}',
    )

    # Should match: same category
    actions = await rule_service.evaluate_for_item(
        spare_part_id=None,
        category="sensors",
        quantity=3,
        unit_price=100.0,
    )
    assert len(actions) == 1

    # Should not match: different category
    actions = await rule_service.evaluate_for_item(
        spare_part_id=None,
        category="valves",
        quantity=3,
        unit_price=100.0,
    )
    assert len(actions) == 0


@pytest.mark.asyncio
async def test_apply_rules_to_multiple_items(rule_service: ProductRuleService):
    """apply_rules should evaluate rules for each item in the list."""
    await rule_service.create_rule(
        rule_type="volume_discount",
        condition_json='{"field":"quantity","op":"gte","value":50}',
        action_json='{"type":"discount","value":5}',
    )

    items = [
        {"spare_part_id": 1, "category": None, "quantity": 100, "unit_price": 10.0},
        {"spare_part_id": 2, "category": None, "quantity": 5, "unit_price": 50.0},
    ]
    modifications = await rule_service.apply_rules(items)
    # Only first item should trigger
    assert len(modifications) == 1
    assert modifications[0]["item_index"] == 0


@pytest.mark.asyncio
async def test_delete_rule(rule_service: ProductRuleService):
    """Deleting a rule should remove it from the list."""
    rule = await rule_service.create_rule(
        rule_type="bundle_suggest",
        condition_json='{"field":"quantity","op":"gte","value":1}',
        action_json='{"type":"suggest","product_id":42}',
    )

    result = await rule_service.delete_rule(rule.id)
    assert result is True

    rules = await rule_service.list_rules()
    assert len(rules) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_rule(rule_service: ProductRuleService):
    """Deleting a non-existent rule should raise NotFoundException."""
    from app.core.exceptions import NotFoundException

    with pytest.raises(NotFoundException):
        await rule_service.delete_rule(99999)
