"""Round-19 Phase 8 — execute HARDENING_DESIGN_V2 roadmap, Phase 1 critical items.

Single migration covering schema deltas for 7 of the 15 findings shipped
this batch. Idempotent (IF NOT EXISTS / DO blocks).

D-006 ``login_lockouts``     — per-account login rate limit persistence
                                 so a restart doesn't clear lockouts
D-008 ``tenant_settings.at_risk_threshold`` — per-tenant configurable
                                 Cockpit threshold (was hardcoded 40)
D-010 ``cross_tenant_attempts`` — log every blocked cross-tenant probe
D-019 ``background_job_dlq``   — DLQ for failed scheduler jobs
D-023 ``active_sessions``      — JTI table so logout-everywhere works
D-027 ``sign_otp_tokens.tsa_token`` — slot for RFC 3161 TSA stamp
                                 (D-027 not yet wired but column ready)

Revision ID: 20260702_phase8_roadmap
Revises: 20260701_phase7_occ_extend
"""

from __future__ import annotations

from alembic import op


revision = "20260702_phase8_roadmap"
down_revision = "20260701_phase7_occ_extend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── D-006: login lockouts ───────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS login_lockouts (
            email_lower       VARCHAR(320) PRIMARY KEY,
            failed_count      INTEGER NOT NULL DEFAULT 0,
            last_failure_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            locked_until      TIMESTAMPTZ,
            last_locked_ip    INET
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_login_lockouts_locked_until "
        "ON login_lockouts (locked_until) WHERE locked_until IS NOT NULL"
    )

    # ── D-008: at_risk_threshold on tenant_settings ────────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'tenant_settings') THEN
            ALTER TABLE tenant_settings
              ADD COLUMN IF NOT EXISTS at_risk_threshold INTEGER NOT NULL DEFAULT 40
              CHECK (at_risk_threshold BETWEEN 0 AND 100);
          END IF;
        END $$;
        """
    )

    # ── D-010: cross-tenant probe log ──────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cross_tenant_attempts (
            id                 BIGSERIAL PRIMARY KEY,
            user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_tenant        INTEGER NOT NULL,
            attempted_entity   VARCHAR(40) NOT NULL,
            attempted_id       BIGINT NOT NULL,
            attempted_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            ip                 INET,
            ua                 TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cta_user_time "
        "ON cross_tenant_attempts (user_id, attempted_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cta_tenant_time "
        "ON cross_tenant_attempts (user_tenant, attempted_at DESC)"
    )

    # ── D-019: background-job DLQ ──────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS background_job_dlq (
            id            BIGSERIAL PRIMARY KEY,
            job_name      VARCHAR(60) NOT NULL,
            payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
            error         TEXT NOT NULL,
            failed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            retry_count   INTEGER NOT NULL DEFAULT 0,
            resolved_at   TIMESTAMPTZ,
            resolved_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            note          TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dlq_unresolved "
        "ON background_job_dlq (job_name, failed_at) "
        "WHERE resolved_at IS NULL"
    )

    # ── D-023: active sessions table ───────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS active_sessions (
            jti           VARCHAR(64) PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at    TIMESTAMPTZ NOT NULL,
            ip            INET,
            ua            TEXT,
            last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_active_sessions_user "
        "ON active_sessions (user_id, last_seen_at DESC)"
    )

    # ── D-027 (slot only): TSA token on sign_otp_tokens ────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'sign_otp_tokens') THEN
            ALTER TABLE sign_otp_tokens
              ADD COLUMN IF NOT EXISTS tsa_token BYTEA;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'sign_otp_tokens') THEN
            ALTER TABLE sign_otp_tokens DROP COLUMN IF EXISTS tsa_token;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'tenant_settings') THEN
            ALTER TABLE tenant_settings DROP COLUMN IF EXISTS at_risk_threshold;
          END IF;
        END $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS active_sessions")
    op.execute("DROP TABLE IF EXISTS background_job_dlq")
    op.execute("DROP TABLE IF EXISTS cross_tenant_attempts")
    op.execute("DROP TABLE IF EXISTS login_lockouts")
