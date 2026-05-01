"""custom_field_values.value_date: DateTime → Date

Revision ID: 20260502_value_date_to_date
Revises: 20260428_v13_audit_tenant
Create Date: 2026-05-02

The CustomFieldValue.value_date column was declared as
DateTime(timezone=True) but the field-type sibling on CustomField only
accepts the literal "date". Storing a timestamp causes off-by-one
display in non-UTC time zones once the value round-trips through
.isoformat() and back. Round-2 audit DB-5.

Cast strategy: PostgreSQL's `::date` cast drops the time component,
which is the desired behavior. The setter in custom_field_service.py
is updated to write `date.fromisoformat(value)` rather than
`datetime.fromisoformat(...).replace(tzinfo=...)` so newly-written
rows match the column type going forward.

Idempotent: each ALTER COLUMN is no-op if the column is already in
the target type, so re-running is safe.
"""

from alembic import op


revision = "20260502_value_date_to_date"
down_revision = "20260428_v13_audit_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: cast TIMESTAMPTZ → DATE drops time of day. The audit
    # confirmed no caller relies on the timestamp component (only the
    # date is used in serialization at custom_field_service.py:78).
    op.execute(
        """
        ALTER TABLE custom_field_values
        ALTER COLUMN value_date TYPE DATE
        USING (value_date AT TIME ZONE 'UTC')::date
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE custom_field_values
        ALTER COLUMN value_date TYPE TIMESTAMPTZ
        USING (value_date::timestamp AT TIME ZONE 'UTC')
        """
    )
