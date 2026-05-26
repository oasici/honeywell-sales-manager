"""Round-19 Phase 6 — finishing F-012 schema bits.

F-012 ``opportunities.fx_rate_to_base`` — FX rate snapshot stamped
at create/update time so multi-currency forecast totals are stable
even when FX moves. Same pattern used by Stripe / Salesforce for
report-time freeze of historical rates.

F-014 needs no schema (in-process debouncer).

Revision ID: 20260630_phase6_finishing
Revises: 20260629_phase4_hardening
"""

from __future__ import annotations

from alembic import op


revision = "20260630_phase6_finishing"
down_revision = "20260629_phase4_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE opportunities "
        "ADD COLUMN IF NOT EXISTS fx_rate_to_base NUMERIC(18, 8)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE opportunities DROP COLUMN IF EXISTS fx_rate_to_base")
