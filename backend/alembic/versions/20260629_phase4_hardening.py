"""Round-19 Phase 4 — security + compliance + data integrity.

Single migration covering the 7 Phase 4 items. All idempotent so
re-running on existing DBs is safe.

F-001 ``tenant_dek`` table — per-tenant envelope encryption.
  Each tenant gets a Fernet DEK (32 random bytes), wrapped by the
  app-level Fernet KEK (today: ``ENCRYPTION_KEY`` env var; tomorrow:
  AWS KMS / Vault — swap point isolated in ``app/core/crypto_v2.py``).
  Per-tenant DEK isolation is the security model; KEK swap is an
  infrastructure detail.

F-005 ``admin_action_nonces`` table — one-shot idempotency keys for
  destructive admin actions (merge, KVKK export, etc.). Prevents
  double-click double-merge AND replay attacks.

F-006 ``sign_otp_tokens`` table — replaces the unsigned long-lived
  sign tokens with short-lived OTP-gated codes. Recipient identity
  binding is now enforceable.

F-007 ``deleted_at`` + ``deleted_by`` columns on every soft-deletable
  entity (customers, leads, opportunities, quotes, contracts,
  invoices, email_requests). Existing rows: deleted_at IS NULL = active.

F-011 ``user_roles`` table — many-to-many role assignment.
  Pre-Round-19 ``users.role`` was a single string. New shape lets
  one user hold multiple sub-roles (ops_users + ops_data, etc.).
  Backfill copies existing ``role`` into the new table.

F-023 ``kvkk_export_requests`` table — request → approve → execute
  flow. One operator requests; another operator approves; export
  runs only after approval. Closes the single-operator PII exfil path.

F-024 ``email_optouts`` table + ``email_sequences.unsubscribe_required``
  column. Unsubscribe link token issued per recipient per sequence;
  opt-out recorded immutably.

Revision ID: 20260629_phase4_hardening
Revises: 20260628_phase3_hardening
"""

from __future__ import annotations

from alembic import op


revision = "20260629_phase4_hardening"
down_revision = "20260628_phase3_hardening"
branch_labels = None
depends_on = None


_SOFT_DELETABLE = (
    "customers",
    "leads",
    "opportunities",
    "quotes",
    "contracts",
    "invoices",
    "email_requests",
)


def upgrade() -> None:
    # ── F-001: per-tenant DEK ──────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_dek (
            tenant_id     INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE RESTRICT,
            wrapped_dek   BYTEA NOT NULL,                    -- DEK encrypted with KEK
            kek_version   VARCHAR(40) NOT NULL DEFAULT 'env-v1',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            rotated_at    TIMESTAMPTZ
        )
        """
    )

    # ── F-005: admin action nonces ─────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_action_nonces (
            nonce         VARCHAR(64) PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action_type   VARCHAR(40) NOT NULL,    -- merge_customer | kvkk_export | ...
            expires_at    TIMESTAMPTZ NOT NULL,
            consumed_at   TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_admin_nonces_expires "
        "ON admin_action_nonces (expires_at) WHERE consumed_at IS NULL"
    )

    # ── F-006: e-Sign OTP tokens ───────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sign_otp_tokens (
            id                  BIGSERIAL PRIMARY KEY,
            contract_id         INTEGER NOT NULL,            -- FK left out; legacy contracts may differ
            tenant_id           INTEGER NOT NULL,
            token_hash          VARCHAR(64) NOT NULL UNIQUE,  -- sha256 of the URL token
            recipient_email     VARCHAR(320) NOT NULL,
            otp_hash            VARCHAR(64),                  -- sha256(otp_code), populated on send-OTP
            otp_sent_at         TIMESTAMPTZ,
            otp_send_count      INTEGER NOT NULL DEFAULT 0,
            otp_attempts        INTEGER NOT NULL DEFAULT 0,
            otp_verified_at     TIMESTAMPTZ,
            signed_at           TIMESTAMPTZ,
            ip_used             INET,
            ua_used             TEXT,
            expires_at          TIMESTAMPTZ NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sign_otp_contract "
        "ON sign_otp_tokens (contract_id)"
    )

    # ── F-007: soft delete columns ─────────────────────────────────
    for table in _SOFT_DELETABLE:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM information_schema.tables
                         WHERE table_name = '{table}') THEN
                ALTER TABLE {table}
                  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS deleted_by INTEGER
                    REFERENCES users(id) ON DELETE SET NULL,
                  ADD COLUMN IF NOT EXISTS delete_reason VARCHAR(500);
                CREATE INDEX IF NOT EXISTS ix_{table}_active
                  ON {table} (id) WHERE deleted_at IS NULL;
              END IF;
            END $$;
            """
        )

    # ── F-011: user_roles many-to-many + backfill ──────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role         VARCHAR(40) NOT NULL,
            granted_by   INTEGER REFERENCES users(id),
            granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, role)
        )
        """
    )
    # Backfill: any existing ``users.role`` becomes a row in user_roles.
    # Plus the historical 'operations' role gets expanded into the new
    # sub-roles so existing ops users keep working without a config
    # update.
    op.execute(
        """
        INSERT INTO user_roles (user_id, role)
        SELECT id, role FROM users
        WHERE role IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO user_roles (user_id, role)
        SELECT id, sub_role
        FROM users,
             unnest(ARRAY['ops_users','ops_data','ops_billing']) AS sub_role
        WHERE role = 'operations'
        ON CONFLICT DO NOTHING
        """
    )

    # ── F-023: KVKK export request flow ────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS kvkk_export_requests (
            id              BIGSERIAL PRIMARY KEY,
            tenant_id       INTEGER NOT NULL,
            subject_lookup  VARCHAR(320) NOT NULL,           -- email / vergi_no / phone
            subject_kind    VARCHAR(30) NOT NULL,            -- email | vergi_no | phone
            status          VARCHAR(20) NOT NULL DEFAULT 'requested',
              -- requested | approved | executing | done | rejected | failed
            requested_by    INTEGER NOT NULL REFERENCES users(id),
            requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            approved_by     INTEGER REFERENCES users(id),
            approved_at     TIMESTAMPTZ,
            executed_at     TIMESTAMPTZ,
            artifact_url    VARCHAR(500),                    -- S3 / local path; null until done
            reject_reason   TEXT,
            CHECK (approved_by IS NULL OR approved_by != requested_by)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kvkk_exports_status "
        "ON kvkk_export_requests (tenant_id, status, requested_at)"
    )

    # ── F-024: email opt-out registry ──────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_optouts (
            id                BIGSERIAL PRIMARY KEY,
            tenant_id         INTEGER NOT NULL,
            email             VARCHAR(320) NOT NULL,
            opted_out_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            source            VARCHAR(40) NOT NULL DEFAULT 'unsubscribe_link',
              -- unsubscribe_link | manual_admin | bounce | complaint
            sequence_id       INTEGER,                       -- nullable; opt-out can be global
            unsubscribe_token VARCHAR(64) UNIQUE,            -- the token from the email link
            UNIQUE (tenant_id, email, sequence_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_optouts_email "
        "ON email_optouts (tenant_id, email)"
    )
    # If a sequences table exists, add a "unsubscribe_required" flag
    # so the editor can refuse to save sequences without an
    # {{unsubscribe_link}} token. Guarded for partial deploys.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'email_sequences') THEN
            ALTER TABLE email_sequences
              ADD COLUMN IF NOT EXISTS unsubscribe_required BOOLEAN NOT NULL DEFAULT TRUE,
              ADD COLUMN IF NOT EXISTS consent_source VARCHAR(60);
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
                     WHERE table_name = 'email_sequences') THEN
            ALTER TABLE email_sequences
              DROP COLUMN IF EXISTS consent_source,
              DROP COLUMN IF EXISTS unsubscribe_required;
          END IF;
        END $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS email_optouts")
    op.execute("DROP TABLE IF EXISTS kvkk_export_requests")
    op.execute("DROP TABLE IF EXISTS user_roles")
    for table in _SOFT_DELETABLE:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM information_schema.tables
                         WHERE table_name = '{table}') THEN
                DROP INDEX IF EXISTS ix_{table}_active;
                ALTER TABLE {table}
                  DROP COLUMN IF EXISTS delete_reason,
                  DROP COLUMN IF EXISTS deleted_by,
                  DROP COLUMN IF EXISTS deleted_at;
              END IF;
            END $$;
            """
        )
    op.execute("DROP TABLE IF EXISTS sign_otp_tokens")
    op.execute("DROP TABLE IF EXISTS admin_action_nonces")
    op.execute("DROP TABLE IF EXISTS tenant_dek")
