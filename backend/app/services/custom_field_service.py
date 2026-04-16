"""Custom field service — CRUD for user-defined entity fields and values."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_field import CustomField, CustomFieldValue


class CustomFieldService:
    """Manages custom field definitions and their values on entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_fields(self, entity_type: str) -> list[dict]:
        """Get all custom field definitions for an entity type."""
        result = await self._db.execute(
            select(CustomField)
            .where(CustomField.entity_type == entity_type)
            .order_by(CustomField.sort_order, CustomField.id)
        )
        fields = result.scalars().all()
        return [_field_to_dict(f) for f in fields]

    async def create_field(self, **kwargs) -> CustomField:
        """Create a new custom field definition."""
        field = CustomField(**kwargs)
        self._db.add(field)
        await self._db.flush()
        return field

    async def delete_field(self, field_id: int) -> bool:
        """Delete a custom field and all its values. Returns True if found."""
        result = await self._db.execute(
            select(CustomField).where(CustomField.id == field_id)
        )
        field = result.scalar_one_or_none()
        if not field:
            return False

        # Delete associated values
        values_result = await self._db.execute(
            select(CustomFieldValue).where(CustomFieldValue.custom_field_id == field_id)
        )
        for value in values_result.scalars().all():
            await self._db.delete(value)

        await self._db.delete(field)
        await self._db.flush()
        return True

    async def get_values(self, entity_type: str, entity_id: int) -> dict:
        """Get all custom field values for a specific entity instance.

        Returns a dict mapping field_name -> value.
        """
        result = await self._db.execute(
            select(CustomFieldValue)
            .where(
                CustomFieldValue.entity_type == entity_type,
                CustomFieldValue.entity_id == entity_id,
            )
        )
        values = result.scalars().all()

        output: dict[str, str | float | str | None] = {}
        for val in values:
            field = val.field
            if not field:
                continue
            if val.value_number is not None:
                output[field.field_name] = val.value_number
            elif val.value_date is not None:
                output[field.field_name] = val.value_date.isoformat() if val.value_date else None
            else:
                output[field.field_name] = val.value_text
        return output

    async def set_value(
        self,
        field_id: int,
        entity_type: str,
        entity_id: int,
        value: str | float | None,
    ) -> CustomFieldValue:
        """Set or update a custom field value for a specific entity."""
        # Check if value already exists
        result = await self._db.execute(
            select(CustomFieldValue).where(
                CustomFieldValue.custom_field_id == field_id,
                CustomFieldValue.entity_type == entity_type,
                CustomFieldValue.entity_id == entity_id,
            )
        )
        existing = result.scalar_one_or_none()

        # Determine which column to write to based on field type
        field_result = await self._db.execute(
            select(CustomField).where(CustomField.id == field_id)
        )
        field = field_result.scalar_one_or_none()
        if not field:
            raise ValueError("Ozel alan bulunamadi")

        value_text = None
        value_number = None
        value_date = None

        if field.field_type == "number":
            value_number = float(value) if value is not None else None
        elif field.field_type == "date":
            if isinstance(value, str) and value:
                value_date = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            else:
                value_date = None
        else:
            value_text = str(value) if value is not None else None

        if existing:
            existing.value_text = value_text
            existing.value_number = value_number
            existing.value_date = value_date
            await self._db.flush()
            return existing

        new_value = CustomFieldValue(
            custom_field_id=field_id,
            entity_type=entity_type,
            entity_id=entity_id,
            value_text=value_text,
            value_number=value_number,
            value_date=value_date,
        )
        self._db.add(new_value)
        await self._db.flush()
        return new_value


def _field_to_dict(f: CustomField) -> dict:
    return {
        "id": f.id,
        "entity_type": f.entity_type,
        "field_name": f.field_name,
        "field_type": f.field_type,
        "options_json": f.options_json,
        "is_required": f.is_required,
        "sort_order": f.sort_order,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
