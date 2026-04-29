"""Application configuration via environment variables."""

from __future__ import annotations

import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Environment ──
    ENV: str = "development"  # development | staging | production

    # ── Database ──
    DATABASE_URL: str = ""

    # ── Schema management (production hardening) ──
    # In regulated production, schema drift must be handled via Alembic only.
    AUTO_CREATE_TABLES: bool = False  # dev convenience only
    AUTO_SCHEMA_SYNC: bool = False  # dev convenience only (ALTER TABLE ADD COLUMN IF NOT EXISTS)

    # ── Redis ──
    # Retired. Default empty so ``app/core/redis_client.py`` returns
    # ``None`` and every cache/limiter/revoker falls back to in-memory.
    # Documented in detail in that module's docstring.
    REDIS_URL: str = ""

    # ── Auth / JWT ──
    JWT_SECRET_KEY: str = secrets.token_hex(32)  # Random per-start in dev; MUST set in .env for prod
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Default Admin ──
    DEFAULT_ADMIN_EMAIL: str = "admin@honeywell.com"
    DEFAULT_ADMIN_PASSWORD: str = ""

    @model_validator(mode="after")
    def _validate_production_settings(self):
        import logging as _log
        if self.ENV == "production":
            if not self.DATABASE_URL:
                raise ValueError("DATABASE_URL must be set in production environment")
            if len(self.JWT_SECRET_KEY) < 32:
                _log.getLogger(__name__).warning(
                    "JWT_SECRET_KEY should be at least 32 characters in production"
                )
            origins = [o.strip().lower() for o in self.CORS_ORIGINS.split(",") if o.strip()]
            local_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
            if local_origins:
                raise ValueError(
                    "CORS_ORIGINS contains localhost entries — remove for strict production: "
                    + ", ".join(local_origins)
                )
            # Reject wildcard CORS in production. ``*`` works with
            # ``allow_credentials=False`` only; combined with our
            # JWT cookie auth it would either silently break auth
            # or open the API to every site on the internet — both
            # bad. Operators must list explicit origins.
            if "*" in origins:
                raise ValueError(
                    "CORS_ORIGINS=* is forbidden in production. "
                    "List explicit origins (e.g. https://app.example.com)."
                )
        return self

    # ── CORS ──
    CORS_ORIGINS: str = "http://localhost,http://localhost:80,http://localhost:5173,https://honeywell-frontend.onrender.com"

    # ── Microsoft Graph API ──
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    GRAPH_USER_EMAIL: str = ""
    GRAPH_WEBHOOK_SECRET: str = ""

    # ── Internal email domains (skip parsing) ──
    INTERNAL_EMAIL_DOMAINS: str = "honeywell.com,honeywell.com.tr"

    # ── SMTP ──
    SMTP_HOST: str = "smtp.office365.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = ""

    # ── AI / LLM ──
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL_NAME: str = "claude-sonnet-4-20250514"
    AI_MAX_TOKENS: int = 1024
    AI_TEMPERATURE: float = 1.0
    AI_MAX_RETRIES: int = 3
    AI_TIMEOUT_SECONDS: int = 30
    AI_FALLBACK_STRATEGY: str = "claude-first"  # claude-first | regex-first

    # ── Notification Channels ──
    SLACK_WEBHOOK_URL: str = ""
    TEAMS_WEBHOOK_URL: str = ""

    # ── Company ──
    COMPANY_NAME: str = "Honeywell Turkey"
    COMPANY_ADDRESS: str = "Istanbul, Turkey"
    COMPANY_PHONE: str = "+90 212 000 0000"
    COMPANY_TAX_ID: str = ""

    # ── Quote ──
    QUOTE_PREFIX: str = "HW-2026-"
    DEFAULT_TAX_RATE: float = 20.0
    DEFAULT_CURRENCY: str = "TRY"
    QUOTE_VALIDITY_DAYS: int = 30

    # ── Paths ──
    QUOTES_DIR: str = "data/quotes"
    UPLOADS_DIR: str = "data/uploads"
    TEMPLATES_DIR: str = "app/templates"

    # ── Scheduling ──
    EMAIL_POLL_INTERVAL_MINUTES: int = 5

    # ── Rate Limiting ──
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_API: str = "100/minute"
    # AI endpoints — protect against Claude cost amplification.
    # Per-user (falls back to IP if unauthenticated).
    RATE_LIMIT_AI: str = "60/minute"
    # File uploads — bounds disk/memory pressure on top of size limits + PDF semaphore.
    RATE_LIMIT_UPLOAD: str = "10/minute"
    # V12 multi-tenant: per-tenant AI/upload caps layered above the
    # per-user limits so one tenant can't burn the whole instance
    # budget by rotating through users. No-op when
    # current_user.tenant_id is None (legacy single-tenant deploys).
    RATE_LIMIT_TENANT_AI: str = "1000/minute"
    RATE_LIMIT_TENANT_UPLOAD: str = "200/minute"

    # ── Cross-tenant probe alerting (V13 security signal) ──
    # When a single user accumulates >= ``CROSS_TENANT_ALERT_THRESHOLD``
    # blocked cross-tenant accesses inside ``CROSS_TENANT_ALERT_WINDOW_SECONDS``,
    # a Sentry ``capture_message`` fires once per
    # ``CROSS_TENANT_ALERT_COOLDOWN_SECONDS``. Set threshold to 0
    # to disable the escalation entirely (Prometheus counter +
    # Sentry breadcrumb still fire).
    CROSS_TENANT_ALERT_THRESHOLD: int = 10
    CROSS_TENANT_ALERT_WINDOW_SECONDS: int = 60
    CROSS_TENANT_ALERT_COOLDOWN_SECONDS: int = 300

    # ── Database Pool ──
    # Sized for gunicorn -w 4 workers. Total ceiling = workers * (pool + overflow).
    # With defaults: 4 * (20 + 10) = 120 — well below typical pg max_connections=200
    # while leaving headroom for migrations/admin. Tune down on small Postgres tiers
    # (Render free = 97 max_connections → use DB_POOL_SIZE=10, DB_MAX_OVERFLOW=5).
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 300

    # ── KVKK / Data Retention ──
    # Off by default — turning this on causes daily auto-anonymization of
    # PII on records older than the thresholds below. Once anonymized,
    # the data is unrecoverable, so we make the operator explicitly opt in
    # per environment instead of relying on a code-default.
    KVKK_AUTO_ANONYMIZE_ENABLED: bool = False
    # Email request bodies/subjects/sender addresses older than N days are
    # nulled. Defaults to 2 years per the runbook.
    KVKK_EMAIL_RETENTION_DAYS: int = 730
    # Customers whose latest closed opportunity closed more than N days ago
    # (and have no active opportunities) get their contact PII anonymized.
    # Defaults to 3 years.
    KVKK_OPPORTUNITY_RETENTION_DAYS: int = 1095

    # ── Security ──
    ALLOWED_UPLOAD_EXTENSIONS: str = ".csv,.xlsx,.xls"
    MAX_UPLOAD_SIZE_MB: int = 10

    # PDF parsing safety limits (DoS mitigation)
    PDF_PARSE_TIMEOUT_SECONDS: int = 12
    PDF_PARSE_MAX_PAGES: int = 12
    PDF_PARSE_CONCURRENCY: int = 2

    # ── Demo/Seed (non-production) ──
    # If blank at seed time, a random password is generated and returned in response (never logged).
    DEMO_REP_PASSWORD: str = ""
    DEMO_OPS_PASSWORD: str = ""
    ENABLE_DEMO_SEED: bool = False

    # ── Error Tracking ──
    SENTRY_DSN: str = ""
    # Random string required to hit /api/debug/sentry-test. Leave empty
    # in prod once Sentry is verified to disable the endpoint entirely.
    SENTRY_TEST_TOKEN: str = ""
    # Comma-separated Sentry project IDs allowed to tunnel through
    # /api/sentry-tunnel. Prevents our backend from being abused as an
    # open relay to arbitrary Sentry orgs. Only the frontend project.
    SENTRY_ALLOWED_PROJECT_IDS: str = ""

    # ── Google Calendar OAuth ──
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/calendar/callback"

    # ── Qdrant Vector DB ──
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION_DEALS: str = "deals"
    QDRANT_COLLECTION_INTERACTIONS: str = "interactions"
    QDRANT_COLLECTION_COMPETITORS: str = "competitors"

    # ── Feature Flags ──
    # Each flag documents its dependencies and consumers.

    # --- RAG / Vector Search ---
    # Depends on: QDRANT_URL
    # Required by: semantic search, deal similarity, competitor intel vectors
    FEATURE_RAG: bool = False

    # --- Board & Pipeline ---
    # Depends on: DATABASE_URL
    # Required by: v2 Kanban board, pipeline snapshot scheduler task
    FEATURE_V2_BOARD: bool = False

    # --- V4 Intelligence Backbone (Feature Store) ---
    # Depends on: DATABASE_URL
    # Required by: daily snapshots (opportunity/account/rep), momentum, buyer state, network benchmarks
    FEATURE_V4_FEATURE_STORE: bool = False

    # --- V4 additive read-model (no write-path changes) ---
    # Depends on: DATABASE_URL
    # Exposes read-only projection endpoints (e.g. normalized sales_event timeline).
    FEATURE_V4_ADDITIVE_READMODEL: bool = False

    # --- V4 shadow sales_events table (nightly sync; no CRM writer changes) ---
    # Depends on: DATABASE_URL
    # Materializes v4_sales_events_shadow from activity_logs, opportunity_events, revenue_signals.
    FEATURE_V4_SALES_EVENTS_SHADOW: bool = False

    # --- V4 deal replay snapshots (derived from additive timeline; manager/ops materialize) ---
    # Depends on: DATABASE_URL (uses same timeline reads as additive read-model; no CRM writer changes)
    FEATURE_V4_DEAL_REPLAY: bool = False

    # --- V4 Sales DNA (read-only miner → v4_sales_dna_snapshots; manager/ops materialize) ---
    FEATURE_V4_SALES_DNA: bool = False

    # Nightly learning batch caps (UTC yesterday); scheduler jobs skip when flags off.
    V4_SALES_DNA_NIGHTLY_MAX_OPPORTUNITIES: int = 300
    V4_DEAL_REPLAY_NIGHTLY_MAX_OPPORTUNITIES: int = 200

    # --- V5 Intelligence Platform ---
    # Depends on: FEATURE_V4_FEATURE_STORE (reads OFD), FEATURE_V4_SALES_EVENTS_SHADOW (reads shadow)
    # Required by: objection intel, timing engine, benchmark gap, DNA pattern miner,
    # deal similarity, rep DNA profiles, network anomaly detection.
    FEATURE_V5_INTELLIGENCE: bool = False
    V5_NIGHTLY_MAX_OPPORTUNITIES: int = 500

    # --- V6 Real-time recompute ---
    # Depends on: FEATURE_V4_FEATURE_STORE (writes OFD)
    # When ON, ``activity_logger.log_activity`` triggers a per-opp OFD
    # recompute + decision-gap rebuild + timing-window refresh on every
    # write. Off by default so we can stage rollout per tenant.
    FEATURE_V6_REALTIME: bool = False

    # --- V7 LLM-hybrid objection detection ---
    # Depends on: ANTHROPIC_API_KEY, FEATURE_V5_INTELLIGENCE.
    # When ON, the keyword detector is augmented with a Claude pass
    # for paraphrased objections (call transcripts, long emails).
    # Off by default so Claude cost stays explicit per tenant.
    FEATURE_V7_LLM_OBJECTION: bool = False
    # Threshold above which the LLM pass kicks in even when the
    # keyword pass already returned hits — used for ambiguous text.
    V7_LLM_OBJECTION_TEXT_THRESHOLD: int = 800

    # --- V9 V2/V3 gap closure ---
    # Sprint K — bidirectional CRM sync (Salesforce / HubSpot).
    FEATURE_V9_CRM_SYNC: bool = False
    # Sprint L — Calendar OAuth + meeting auto-log.
    FEATURE_V9_CALENDAR_OAUTH: bool = False
    # Sprint N — semantic NL search over transcript + email + opp text.
    FEATURE_V9_NL_SEARCH: bool = False

    # --- V12 transformer-based sequence embedding ---
    # Depends on: sentence-transformers package + the multilingual MiniLM
    # weights already loaded by the spare parts catalog (no extra cost
    # when FEATURE_RAG is also on; otherwise warm-up = a few hundred ms).
    # When ON, ``deal_similarity_service`` adds a 4th component (semantic
    # transformer cosine, weight 0.2) to the V8 blend; falls back to
    # V8 3-component when the transformer vector is missing.
    FEATURE_TRANSFORMER_SEQ_EMBEDDING: bool = False

    # --- V10 spare parts intelligence (read-only layer) ---
    # Depends on: DATABASE_URL only. No schema changes — pure derivation
    # over SparePart × PriceEntry × QuoteItem × Quote × Opportunity.
    # When ON, exposes /v10/parts-intel/* endpoints (velocity Pareto,
    # dead stock ledger, demand heatmap, inflation tax, stale pricing,
    # margin health, EOL risk, last-time-buy, master data health,
    # duplicate detection, substitution patterns, cross-customer demand,
    # segment affinity) and lights up the Spare Parts Intelligence
    # dashboard + SparePart detail enhancements.
    FEATURE_V10_PARTS_INTEL: bool = False

    # --- Board & Pipeline ---
    # Depends on: DATABASE_URL
    # Required by: Tasks CRUD + recommended actions panel (Sprint 2 prerequisite)
    FEATURE_TASKS: bool = False

    # --- AI-Powered Features ---
    # Depends on: ANTHROPIC_API_KEY
    # Required by: email summary generation, deal summary cards
    FEATURE_AI_SUMMARIES: bool = False

    # Depends on: ANTHROPIC_API_KEY, FEATURE_V2_BOARD
    # Required by: AI-generated pipeline stage suggestions
    FEATURE_AI_PIPELINE_SUGGESTIONS: bool = False

    # Depends on: ANTHROPIC_API_KEY
    # Required by: email triage classification, priority routing
    FEATURE_AI_TRIAGE: bool = False

    # Depends on: ANTHROPIC_API_KEY
    # Required by: deal risk scoring, risk signal emission
    FEATURE_AI_DEAL_RISK: bool = False

    # Depends on: ANTHROPIC_API_KEY, FEATURE_RAG
    # Required by: competitor crawl scheduler task, battle card generation
    FEATURE_AI_COMPETITIVE_INTEL: bool = False

    # Depends on: ANTHROPIC_API_KEY
    # Required by: forecast predictions, win probability scoring
    FEATURE_AI_PREDICTIONS: bool = False

    # --- Lead & Deal Management ---
    # Depends on: DATABASE_URL
    # Required by: lead status transitions, lifecycle stage tracking
    FEATURE_LEAD_LIFECYCLE: bool = False

    # Depends on: ANTHROPIC_API_KEY
    # Required by: deal health indicators, health score dashboard
    FEATURE_DEAL_HEALTH: bool = False

    # Depends on: ANTHROPIC_API_KEY
    # Required by: guided selling wizard, next-best-action suggestions
    FEATURE_GUIDED_SELLING: bool = False

    # --- Revenue Operations ---
    # Depends on: ANTHROPIC_API_KEY
    # Required by: cockpit endpoints, playbook evaluation, coaching scheduler tasks
    FEATURE_REVENUE_COCKPIT: bool = False

    # --- Approval & Workflow ---
    # Depends on: DATABASE_URL
    # Required by: multi-level quote approval, approval escalation task
    FEATURE_APPROVAL_ROUTING: bool = False

    # Depends on: DATABASE_URL
    # Required by: automated workflow triggers, rule evaluation engine
    FEATURE_WORKFLOW_RULES: bool = False

    # Depends on: DATABASE_URL
    # Required by: KVKK breach workflow, data breach notification pipeline
    FEATURE_BREACH_WORKFLOW: bool = False

    # --- Reporting & Dashboards ---
    # Depends on: DATABASE_URL
    # Required by: custom report builder, scheduled report emails
    FEATURE_REPORT_BUILDER: bool = False

    # Depends on: DATABASE_URL
    # Required by: custom dashboard widget builder
    FEATURE_DASHBOARD_BUILDER: bool = False

    # --- Access Control & Security ---
    # Depends on: DATABASE_URL
    # Required by: team-based data isolation, territory management
    FEATURE_TEAM_ACCESS: bool = False

    # Depends on: DATABASE_URL
    # Required by: per-field role-based visibility rules
    FEATURE_FIELD_PERMISSIONS: bool = False

    # Depends on: REDIS_URL
    # Required by: concurrent session limiting, session revocation
    FEATURE_SESSION_MANAGEMENT: bool = False

    # --- Integrations & API ---
    # Depends on: DATABASE_URL
    # Required by: outgoing webhook dispatch, webhook log UI
    FEATURE_WEBHOOKS: bool = False

    # Depends on: DATABASE_URL, JWT_SECRET_KEY
    # Required by: external REST API access, API key management
    FEATURE_PUBLIC_API: bool = False

    # --- Product & Configuration ---
    # Depends on: DATABASE_URL
    # Required by: product compatibility rules, bundle validation
    FEATURE_PRODUCT_RULES: bool = False

    # Depends on: DATABASE_URL
    # Required by: user-defined entity fields, custom field rendering
    FEATURE_CUSTOM_FIELDS: bool = False

    # --- Progressive Web App ---
    # Depends on: CORS_ORIGINS
    # Required by: offline mode, push notifications, install prompt
    FEATURE_PWA: bool = False

    # --- Campaigns ---
    # Depends on: DATABASE_URL
    # Required by: campaign list/detail pages, ROI tracking
    FEATURE_CAMPAIGNS: bool = False

    # --- Invoicing ---
    # Depends on: DATABASE_URL
    # Required by: invoice list/detail, PDF generation, billing workflow
    FEATURE_INVOICING: bool = False

    # --- E-Signature ---
    # Depends on: DATABASE_URL
    # Required by: document signing workflow, public signing page
    FEATURE_ESIGN: bool = False
    ESIGN_TOKEN_EXPIRE_DAYS: int = 7

    # --- Multi-Pipeline ---
    # Depends on: DATABASE_URL
    # Required by: pipeline list/CRUD, pipeline_id on opportunities
    FEATURE_MULTI_PIPELINE: bool = False

    # --- Territory Management ---
    # Depends on: DATABASE_URL
    # Required by: territory CRUD, user assignments, auto-assign, territory_id on customers/opportunities
    FEATURE_TERRITORIES: bool = False

    # --- Revenue Recognition ---
    # Depends on: DATABASE_URL, contracts
    # Required by: revenue schedule CRUD, monthly entry generation, recognition workflow, dashboard
    FEATURE_REV_REC: bool = False

    # --- Live Chat ---
    # Depends on: DATABASE_URL
    # Required by: visitor session creation, agent assignment, message history, auto-response rules
    FEATURE_LIVE_CHAT: bool = False

    # --- Sequences V2 (Cadence Engine) ---
    # Depends on: DATABASE_URL
    # Required by: idempotent step execution, global exit conditions, step run telemetry,
    #   domain event emission (sequence.step_completed, sequence.completed, sequence.exited)
    FEATURE_SEQUENCES_V2: bool = False

    # --- Behavioral Scoring ---
    # Depends on: DATABASE_URL, FEATURE_SEQUENCES_V2
    # Required by: lead/opportunity dynamic scoring from engagement signals,
    #   auto-enroll/auto-exit triggers, work hub priority ranking
    FEATURE_BEHAVIORAL_SCORING: bool = False

    # --- Buyer Relationship Map ---
    # Depends on: DATABASE_URL
    # Required by: stakeholder CRUD on opportunity/customer, buying committee visualization,
    #   coverage gap alerts, transcript participant enrichment
    FEATURE_BUYER_MAP: bool = False

    MAX_CONCURRENT_SESSIONS: int = 3

    # Convenience flag: set ENABLE_ALL_FEATURES=true to activate everything at once
    ENABLE_ALL_FEATURES: bool = False

    @model_validator(mode="after")
    def _apply_enable_all(self):
        if self.ENABLE_ALL_FEATURES:
            for field_name in self.model_fields:
                if field_name.startswith("FEATURE_") and isinstance(getattr(self, field_name), bool):
                    object.__setattr__(self, field_name, True)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def internal_domains_list(self) -> list[str]:
        return [d.strip().lower() for d in self.INTERNAL_EMAIL_DOMAINS.split(",") if d.strip()]

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",") if e.strip()}

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        """True only in local dev/test. Staging/sandbox/production all return False."""
        return self.ENV in ("development", "dev", "test", "local")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
