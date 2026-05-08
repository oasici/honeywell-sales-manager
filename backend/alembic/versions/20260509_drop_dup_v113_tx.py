"""Round-8 R8-DB-1 — drop duplicate tenant_id indexes on v1.13 tables.

Bootstrap (regenerated after v1.13 landed) creates ORM-canonical
``ix_<tablename>_<colname>`` indexes via ``Base.metadata.create_all()``.
The v1.13 ``20260508_v113_plan_adopt`` migration also creates a second
``tenant_id`` index per table with a shortened name. Both blocks use
``IF NOT EXISTS``, so neither skips the other.

This migration drops the four migration-created short names, leaving the
ORM-canonical long names intact.

Revision ID: 20260509_drop_dup_v113_tx
Revises: 20260508_v113_plan_adopt
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op


revision = "20260509_drop_dup_v113_tx"
down_revision = "20260508_v113_plan_adopt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for idx in (
        "ix_rel_edge_tenant_id",
        "ix_rel_score_tenant_id",
        "ix_ai_attr_def_tenant_id",
        "ix_ai_attr_value_tenant_id",
    ):
        op.execute(f"DROP INDEX IF EXISTS {idx}")


def downgrade() -> None:
    # Recreating duplicates would be a regression; left as no-op.
    pass
