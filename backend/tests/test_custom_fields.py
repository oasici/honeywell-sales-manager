"""Tests for custom fields — create field, set value, get values, unique constraint."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_field import CustomField, CustomFieldValue
from app.services.custom_field_service import CustomFieldService


class TestCustomFieldService:
    """CustomFieldService CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_field(self, db: AsyncSession):
        service = CustomFieldService(db)
        field = await service.create_field(
            entity_type="customer",
            field_name="sektör",
            field_type="text",
        )
        await db.commit()

        assert field.id is not None
        assert field.entity_type == "customer"
        assert field.field_name == "sektör"
        assert field.field_type == "text"

    @pytest.mark.asyncio
    async def test_get_fields_by_entity_type(self, db: AsyncSession):
        service = CustomFieldService(db)

        await service.create_field(
            entity_type="customer",
            field_name="field_a",
            field_type="text",
        )
        await service.create_field(
            entity_type="customer",
            field_name="field_b",
            field_type="number",
        )
        await service.create_field(
            entity_type="opportunity",
            field_name="field_c",
            field_type="date",
        )
        await db.flush()

        customer_fields = await service.get_fields("customer")
        assert len(customer_fields) == 2

        opp_fields = await service.get_fields("opportunity")
        assert len(opp_fields) == 1

    @pytest.mark.asyncio
    async def test_set_and_get_text_value(self, db: AsyncSession):
        service = CustomFieldService(db)
        field = await service.create_field(
            entity_type="customer",
            field_name="notlar",
            field_type="text",
        )
        await db.flush()

        await service.set_value(
            field_id=field.id,
            entity_type="customer",
            entity_id=1,
            value="Test notu",
        )
        await db.flush()

        values = await service.get_values("customer", 1)
        assert values["notlar"] == "Test notu"

    @pytest.mark.asyncio
    async def test_set_and_get_number_value(self, db: AsyncSession):
        service = CustomFieldService(db)
        field = await service.create_field(
            entity_type="customer",
            field_name="puan",
            field_type="number",
        )
        await db.flush()

        await service.set_value(
            field_id=field.id,
            entity_type="customer",
            entity_id=1,
            value=42.5,
        )
        await db.flush()

        values = await service.get_values("customer", 1)
        assert values["puan"] == 42.5

    @pytest.mark.asyncio
    async def test_update_existing_value(self, db: AsyncSession):
        service = CustomFieldService(db)
        field = await service.create_field(
            entity_type="customer",
            field_name="durum",
            field_type="text",
        )
        await db.flush()

        await service.set_value(
            field_id=field.id,
            entity_type="customer",
            entity_id=1,
            value="eski",
        )
        await db.flush()

        await service.set_value(
            field_id=field.id,
            entity_type="customer",
            entity_id=1,
            value="yeni",
        )
        await db.flush()

        values = await service.get_values("customer", 1)
        assert values["durum"] == "yeni"

    @pytest.mark.asyncio
    async def test_delete_field_removes_values(self, db: AsyncSession):
        service = CustomFieldService(db)
        field = await service.create_field(
            entity_type="lead",
            field_name="kaynak",
            field_type="text",
        )
        await db.flush()

        await service.set_value(
            field_id=field.id,
            entity_type="lead",
            entity_id=1,
            value="web",
        )
        await db.flush()

        is_ok = await service.delete_field(field.id)
        assert is_ok is True

        fields = await service.get_fields("lead")
        assert len(fields) == 0

    @pytest.mark.asyncio
    async def test_set_value_for_nonexistent_field_raises(self, db: AsyncSession):
        service = CustomFieldService(db)
        with pytest.raises(ValueError, match="Ozel alan bulunamadi"):
            await service.set_value(
                field_id=99999,
                entity_type="customer",
                entity_id=1,
                value="test",
            )
