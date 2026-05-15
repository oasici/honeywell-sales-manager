"""Round-15 F-002 / Sprint 15j cohort 13 — defense-in-depth tenant_id on engagement + embedding + sequence-run tables.

Continues the cohort 1-12 pattern. This revision covers four tables
with chain-dependent backfills:

  * ``transcripts`` — call/meeting transcript text.
    Backfill chain: ``opportunities.tenant_id`` via opportunity_id
    (nullable) → ``customers.tenant_id`` via customer_id (nullable).
    Rows with neither FK stay NULL on this migration (rare; legacy
    upload paths).
  * ``transcript_embeddings`` — per-transcript embedding (PK =
    transcript_id). **Must run after** the transcripts backfill so
    the cascade is clean.
  * ``email_embeddings`` — per-email_request embedding (PK =
    email_request_id). Backfill from ``email_requests.tenant_id``.
  * ``sequence_step_runs`` — per-(enrollment, step) execution log.
    Backfill from ``sequence_enrollments.tenant_id``.

Nullable on disk per the cohort convention. The audit's parked
F-001 Sprint 15k/l NOT-NULL promotion remains parked.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260603_phase12_tenant_did_cohort13
Revises: 20260602_phase12_tenant_did_cohort12
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op


revision = "20260603_phase12_tenant_did_cohort13"
down_revision = "20260602_phase12_tenant_did_cohort12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. transcripts (chain root) ─────────────────────────────
    op.execute(
        "ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    # Primary: opportunity-derived tenant.
    op.execute(
        """
        UPDATE transcripts t
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE t.tenant_id IS NULL
          AND t.opportunity_id = o.id
          AND o.tenant_id IS NOT NULL
        """
    )
    # Fallback: customer-derived tenant.
    op.execute(
        """
        UPDATE transcripts t
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE t.tenant_id IS NULL
          AND t.customer_id = c.id
          AND c.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transcripts_tenant_id ON transcripts (tenant_id)"
    )

    # ── 2. transcript_embeddings (depends on transcripts above) ──
    op.execute(
        "ALTER TABLE transcript_embeddings ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        """
        UPDATE transcript_embeddings te
        SET tenant_id = t.tenant_id
        FROM transcripts t
        WHERE te.tenant_id IS NULL
          AND te.transcript_id = t.id
          AND t.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transcript_embeddings_tenant_id "
        "ON transcript_embeddings (tenant_id)"
    )

    # ── 3. email_embeddings ─────────────────────────────────────
    op.execute(
        "ALTER TABLE email_embeddings ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        """
        UPDATE email_embeddings ee
        SET tenant_id = er.tenant_id
        FROM email_requests er
        WHERE ee.tenant_id IS NULL
          AND ee.email_request_id = er.id
          AND er.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_embeddings_tenant_id "
        "ON email_embeddings (tenant_id)"
    )

    # ── 4. sequence_step_runs ───────────────────────────────────
    op.execute(
        "ALTER TABLE sequence_step_runs ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        """
        UPDATE sequence_step_runs sr
        SET tenant_id = se.tenant_id
        FROM sequence_enrollments se
        WHERE sr.tenant_id IS NULL
          AND sr.enrollment_id = se.id
          AND se.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sequence_step_runs_tenant_id "
        "ON sequence_step_runs (tenant_id)"
    )


def downgrade() -> None:
    # Reverse declaration order — drop embeddings first so they don't
    # outlive their parent's tenant_id.
    for table in (
        "sequence_step_runs",
        "email_embeddings",
        "transcript_embeddings",
        "transcripts",
    ):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
