"""Index hardening — ensure ORM-declared indexes exist.

Revision ID: 20260427_index_hardening
Revises: 20260426_model_drift_align
Create Date: 2026-04-27

This migration is intentionally idempotent: it inspects existing indexes and
creates any missing ones that are expected by SQLAlchemy models.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260427_index_hardening"
down_revision = "20260426_model_drift_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def has_index(table: str, columns: list[str]) -> bool:
        try:
            idxs = insp.get_indexes(table, schema="public") or []
        except Exception:
            return False
        want = tuple(sorted(columns))
        for idx in idxs:
            cols = idx.get("column_names") or []
            if tuple(sorted(cols)) == want:
                return True
        return False

    # customers(parent_id), customers(territory_id)
    if "customers" in insp.get_table_names(schema="public"):
        if not has_index("customers", ["parent_id"]):
            op.create_index("ix_customers_parent_id", "customers", ["parent_id"])
        if not has_index("customers", ["territory_id"]):
            op.create_index("ix_customers_territory_id", "customers", ["territory_id"])

    # opportunities(pipeline_id), opportunities(territory_id)
    if "opportunities" in insp.get_table_names(schema="public"):
        if not has_index("opportunities", ["pipeline_id"]):
            op.create_index("ix_opportunities_pipeline_id", "opportunities", ["pipeline_id"])
        if not has_index("opportunities", ["territory_id"]):
            op.create_index("ix_opportunities_territory_id", "opportunities", ["territory_id"])

    # sequence_enrollments(lead_id)
    if "sequence_enrollments" in insp.get_table_names(schema="public"):
        if not has_index("sequence_enrollments", ["lead_id"]):
            op.create_index("ix_sequence_enrollments_lead_id", "sequence_enrollments", ["lead_id"])


def downgrade() -> None:
    # Safe no-op downgrade (indexes are non-destructive and may be shared by other deployments)
    pass

