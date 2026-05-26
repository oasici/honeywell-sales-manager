"""Round-19 Phase 2 — schema changes for the second hardening batch.

Single migration covers 6 findings whose schema deltas are tiny and
better landed together than spread across 6 PRs:

F-013 ``token_blocklist`` table — persistent JWT JTI revocation
  list so logouts survive process restart. The in-memory + Redis
  layers already exist (see ``app/core/security.py``); PG is the
  final fallback that *always* answers correctly even when Redis
  is down. ``exp`` column lets a cleanup cron drop expired rows.

F-015 ``workflow_execution_log`` table — per-event chain trace so
  cycle-detection has a place to record blocked invocations and
  ops can investigate runaway rule fires.

F-017 ``quotes.row_version`` — pure optimistic-concurrency lock.
  The existing ``quotes.version`` column is the *document* version
  (v1, v2 superseded — used by F-026); ``row_version`` is the
  monotonic counter every UPDATE bumps to detect concurrent edits.

F-025 ``coaching_hooks.ai_generated`` + ``coaching_hooks.manager_reviewed``
  Mark each hook with its source + manager-review status so the UI
  can warn "🤖 AI önerisi (düzenle)" and the publish path can
  block un-reviewed AI hooks from reaching reps.

F-029 ``tenant_settings`` table — narrow, typed per-tenant config.
  Added ``auto_quote_max_amount`` + ``auto_quote_currency`` here;
  future single-row columns (forecast base currency, OCR page cap,
  AI cost quota, etc.) belong on this same row.

F-030 ``ai_tasks.dismissed_at`` + ``ai_tasks.stale_dismissed`` —
  let a cron mark > 30-day-old open tasks ``stale_dismissed``
  without nuking real dismissal history.

Revision ID: 20260627_phase2_hardening
Revises: 20260626_email_eligibility_gate
"""

from __future__ import annotations

from alembic import op


revision = "20260627_phase2_hardening"
down_revision = "20260626_email_eligibility_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── F-013: token_blocklist ──────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_blocklist (
            jti        VARCHAR(64) PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
            exp        TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            reason     VARCHAR(40)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_token_blocklist_exp "
        "ON token_blocklist (exp)"
    )

    # ── F-015: workflow_execution_log ───────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_execution_log (
            id            BIGSERIAL PRIMARY KEY,
            tenant_id     INTEGER NOT NULL,
            root_event_id VARCHAR(64) NOT NULL,
            rule_id       INTEGER NOT NULL,
            depth         INTEGER NOT NULL,
            outcome       VARCHAR(40) NOT NULL,  -- ran|blocked_depth|blocked_cycle|errored
            note          TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wf_exec_log_root "
        "ON workflow_execution_log (root_event_id, depth)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wf_exec_log_tenant_outcome "
        "ON workflow_execution_log (tenant_id, outcome, created_at)"
    )

    # ── F-017: quotes.row_version ───────────────────────────────────
    op.execute(
        "ALTER TABLE quotes "
        "ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1"
    )

    # ── F-025: coaching_hooks AI provenance ────────────────────────
    # Older databases may not have a coaching_hooks table yet. Wrap in
    # a guarded DO block so the migration is no-op on partial deploys
    # but still adds the columns on full deploys.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'coaching_hooks') THEN
            ALTER TABLE coaching_hooks
              ADD COLUMN IF NOT EXISTS ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
              ADD COLUMN IF NOT EXISTS ai_model_version VARCHAR(64),
              ADD COLUMN IF NOT EXISTS ai_confidence NUMERIC(4,3),
              ADD COLUMN IF NOT EXISTS manager_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
              ADD COLUMN IF NOT EXISTS manager_reviewed_by INTEGER REFERENCES users(id),
              ADD COLUMN IF NOT EXISTS manager_reviewed_at TIMESTAMPTZ;
          END IF;
        END $$;
        """
    )

    # ── F-029: tenant_settings ─────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_settings (
            tenant_id              INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
            auto_quote_max_amount  NUMERIC(18, 2),                -- NULL = no limit
            auto_quote_currency    VARCHAR(3) NOT NULL DEFAULT 'TRY',
            -- placeholders for future Phase 4 / Phase 5 settings:
            base_currency          VARCHAR(3) NOT NULL DEFAULT 'TRY',
            ocr_max_pages          INTEGER NOT NULL DEFAULT 5,
            ai_monthly_quota_usd   NUMERIC(10, 2),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ── F-030: ai_tasks aging columns ──────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'ai_tasks') THEN
            ALTER TABLE ai_tasks
              ADD COLUMN IF NOT EXISTS dismissed_at TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS stale_dismissed BOOLEAN NOT NULL DEFAULT FALSE;
          END IF;
        END $$;
        """
    )

    # ── F-010: approval rule pending meta-changes ──────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_rule_pending_changes (
            id              BIGSERIAL PRIMARY KEY,
            rule_id         INTEGER NOT NULL,
            tenant_id       INTEGER NOT NULL,
            proposed_by     INTEGER NOT NULL REFERENCES users(id),
            proposed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            change_payload  JSONB NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
            reviewed_by     INTEGER REFERENCES users(id),
            reviewed_at     TIMESTAMPTZ,
            review_note     TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_approval_rule_pending_status "
        "ON approval_rule_pending_changes (tenant_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS approval_rule_pending_changes")
    op.execute("DROP TABLE IF EXISTS tenant_settings")
    op.execute("DROP TABLE IF EXISTS workflow_execution_log")
    op.execute("DROP TABLE IF EXISTS token_blocklist")
    op.execute("ALTER TABLE quotes DROP COLUMN IF EXISTS row_version")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'coaching_hooks') THEN
            ALTER TABLE coaching_hooks
              DROP COLUMN IF EXISTS manager_reviewed_at,
              DROP COLUMN IF EXISTS manager_reviewed_by,
              DROP COLUMN IF EXISTS manager_reviewed,
              DROP COLUMN IF EXISTS ai_confidence,
              DROP COLUMN IF EXISTS ai_model_version,
              DROP COLUMN IF EXISTS ai_generated;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'ai_tasks') THEN
            ALTER TABLE ai_tasks
              DROP COLUMN IF EXISTS stale_dismissed,
              DROP COLUMN IF EXISTS dismissed_at;
          END IF;
        END $$;
        """
    )
