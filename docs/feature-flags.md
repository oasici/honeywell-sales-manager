# Feature Flags Reference

Auto-generated from inline annotations in `backend/app/core/config.py`. All feature flags default to `false` and must be explicitly set per environment. Re-run `backend/scripts/generate_feature_flags_doc.py` when flags are added or removed.

> Don't enable a flag in production without running its dependent migrations, verifying staging behavior, and updating the runbook for the affected feature.

## Quick Reference

| Flag | Default | Section | Depends on |
|------|---------|---------|------------|
| `FEATURE_RAG` | `false` | RAG / Vector Search | QDRANT_URL |
| `FEATURE_V2_BOARD` | `false` | Board & Pipeline | DATABASE_URL |
| `FEATURE_V4_FEATURE_STORE` | `false` | V4 Intelligence Backbone (Feature Store) | DATABASE_URL |
| `FEATURE_V4_ADDITIVE_READMODEL` | `false` | V4 additive read-model (no write-path changes) | DATABASE_URL |
| `FEATURE_V4_SALES_EVENTS_SHADOW` | `false` | V4 shadow sales_events table (nightly sync; no CRM writer changes) | DATABASE_URL |
| `FEATURE_TASKS` | `false` | Board & Pipeline | DATABASE_URL |
| `FEATURE_AI_SUMMARIES` | `false` | AI-Powered Features | ANTHROPIC_API_KEY |
| `FEATURE_AI_PIPELINE_SUGGESTIONS` | `false` | AI-Powered Features | ANTHROPIC_API_KEY, FEATURE_V2_BOARD |
| `FEATURE_AI_TRIAGE` | `false` | AI-Powered Features | ANTHROPIC_API_KEY |
| `FEATURE_AI_DEAL_RISK` | `false` | AI-Powered Features | ANTHROPIC_API_KEY |
| `FEATURE_AI_COMPETITIVE_INTEL` | `false` | AI-Powered Features | ANTHROPIC_API_KEY, FEATURE_RAG |
| `FEATURE_AI_PREDICTIONS` | `false` | AI-Powered Features | ANTHROPIC_API_KEY |
| `FEATURE_LEAD_LIFECYCLE` | `false` | Lead & Deal Management | DATABASE_URL |
| `FEATURE_DEAL_HEALTH` | `false` | Lead & Deal Management | ANTHROPIC_API_KEY |
| `FEATURE_GUIDED_SELLING` | `false` | Lead & Deal Management | ANTHROPIC_API_KEY |
| `FEATURE_REVENUE_COCKPIT` | `false` | Revenue Operations | ANTHROPIC_API_KEY |
| `FEATURE_APPROVAL_ROUTING` | `false` | Approval & Workflow | DATABASE_URL |
| `FEATURE_WORKFLOW_RULES` | `false` | Approval & Workflow | DATABASE_URL |
| `FEATURE_BREACH_WORKFLOW` | `false` | Approval & Workflow | DATABASE_URL |
| `FEATURE_REPORT_BUILDER` | `false` | Reporting & Dashboards | DATABASE_URL |
| `FEATURE_DASHBOARD_BUILDER` | `false` | Reporting & Dashboards | DATABASE_URL |
| `FEATURE_TEAM_ACCESS` | `false` | Access Control & Security | DATABASE_URL |
| `FEATURE_FIELD_PERMISSIONS` | `false` | Access Control & Security | DATABASE_URL |
| `FEATURE_SESSION_MANAGEMENT` | `false` | Access Control & Security | REDIS_URL |
| `FEATURE_WEBHOOKS` | `false` | Integrations & API | DATABASE_URL |
| `FEATURE_PUBLIC_API` | `false` | Integrations & API | DATABASE_URL, JWT_SECRET_KEY |
| `FEATURE_PRODUCT_RULES` | `false` | Product & Configuration | DATABASE_URL |
| `FEATURE_CUSTOM_FIELDS` | `false` | Product & Configuration | DATABASE_URL |
| `FEATURE_PWA` | `false` | Progressive Web App | CORS_ORIGINS |
| `FEATURE_CAMPAIGNS` | `false` | Campaigns | DATABASE_URL |
| `FEATURE_INVOICING` | `false` | Invoicing | DATABASE_URL |
| `FEATURE_ESIGN` | `false` | E-Signature | DATABASE_URL |
| `FEATURE_MULTI_PIPELINE` | `false` | Multi-Pipeline | DATABASE_URL |
| `FEATURE_TERRITORIES` | `false` | Territory Management | DATABASE_URL |
| `FEATURE_REV_REC` | `false` | Revenue Recognition | DATABASE_URL, contracts |
| `FEATURE_LIVE_CHAT` | `false` | Live Chat | DATABASE_URL |
| `FEATURE_SEQUENCES_V2` | `false` | Sequences V2 (Cadence Engine) | DATABASE_URL |
| `FEATURE_BEHAVIORAL_SCORING` | `false` | Behavioral Scoring | DATABASE_URL, FEATURE_SEQUENCES_V2 |
| `FEATURE_BUYER_MAP` | `false` | Buyer Relationship Map | DATABASE_URL |

## Detail

### RAG / Vector Search

#### `FEATURE_RAG`

- **Default:** `false`
- **Depends on:** QDRANT_URL
- **Required by:** semantic search, deal similarity, competitor intel vectors
- **Rollback:** Set `FEATURE_RAG=false`, restart backend. No migration to revert.

### Board & Pipeline

#### `FEATURE_V2_BOARD`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** v2 Kanban board, pipeline snapshot scheduler task
- **Rollback:** Set `FEATURE_V2_BOARD=false`, restart backend. No migration to revert.

### V4 Intelligence Backbone (Feature Store)

#### `FEATURE_V4_FEATURE_STORE`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** daily snapshots (opportunity/account/rep), momentum, buyer state, network benchmarks
- **Rollback:** Set `FEATURE_V4_FEATURE_STORE=false`, restart backend. No migration to revert.

### V4 additive read-model (no write-path changes)

#### `FEATURE_V4_ADDITIVE_READMODEL`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Rollback:** Set `FEATURE_V4_ADDITIVE_READMODEL=false`, restart backend. No migration to revert.

### V4 shadow sales_events table (nightly sync; no CRM writer changes)

#### `FEATURE_V4_SALES_EVENTS_SHADOW`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Rollback:** Set `FEATURE_V4_SALES_EVENTS_SHADOW=false`, restart backend. No migration to revert.

### Board & Pipeline

#### `FEATURE_TASKS`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** Tasks CRUD + recommended actions panel (Sprint 2 prerequisite)
- **Rollback:** Set `FEATURE_TASKS=false`, restart backend. No migration to revert.

### AI-Powered Features

#### `FEATURE_AI_SUMMARIES`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** email summary generation, deal summary cards
- **Rollback:** Set `FEATURE_AI_SUMMARIES=false`, restart backend. No migration to revert.

#### `FEATURE_AI_PIPELINE_SUGGESTIONS`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY, FEATURE_V2_BOARD
- **Required by:** AI-generated pipeline stage suggestions
- **Rollback:** Set `FEATURE_AI_PIPELINE_SUGGESTIONS=false`, restart backend. No migration to revert.

#### `FEATURE_AI_TRIAGE`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** email triage classification, priority routing
- **Rollback:** Set `FEATURE_AI_TRIAGE=false`, restart backend. No migration to revert.

#### `FEATURE_AI_DEAL_RISK`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** deal risk scoring, risk signal emission
- **Rollback:** Set `FEATURE_AI_DEAL_RISK=false`, restart backend. No migration to revert.

#### `FEATURE_AI_COMPETITIVE_INTEL`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY, FEATURE_RAG
- **Required by:** competitor crawl scheduler task, battle card generation
- **Rollback:** Set `FEATURE_AI_COMPETITIVE_INTEL=false`, restart backend. No migration to revert.

#### `FEATURE_AI_PREDICTIONS`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** forecast predictions, win probability scoring
- **Rollback:** Set `FEATURE_AI_PREDICTIONS=false`, restart backend. No migration to revert.

### Lead & Deal Management

#### `FEATURE_LEAD_LIFECYCLE`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** lead status transitions, lifecycle stage tracking
- **Rollback:** Set `FEATURE_LEAD_LIFECYCLE=false`, restart backend. No migration to revert.

#### `FEATURE_DEAL_HEALTH`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** deal health indicators, health score dashboard
- **Rollback:** Set `FEATURE_DEAL_HEALTH=false`, restart backend. No migration to revert.

#### `FEATURE_GUIDED_SELLING`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** guided selling wizard, next-best-action suggestions
- **Rollback:** Set `FEATURE_GUIDED_SELLING=false`, restart backend. No migration to revert.

### Revenue Operations

#### `FEATURE_REVENUE_COCKPIT`

- **Default:** `false`
- **Depends on:** ANTHROPIC_API_KEY
- **Required by:** cockpit endpoints, playbook evaluation, coaching scheduler tasks
- **Rollback:** Set `FEATURE_REVENUE_COCKPIT=false`, restart backend. No migration to revert.

### Approval & Workflow

#### `FEATURE_APPROVAL_ROUTING`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** multi-level quote approval, approval escalation task
- **Rollback:** Set `FEATURE_APPROVAL_ROUTING=false`, restart backend. No migration to revert.

#### `FEATURE_WORKFLOW_RULES`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** automated workflow triggers, rule evaluation engine
- **Rollback:** Set `FEATURE_WORKFLOW_RULES=false`, restart backend. No migration to revert.

#### `FEATURE_BREACH_WORKFLOW`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** KVKK breach workflow, data breach notification pipeline
- **Rollback:** Set `FEATURE_BREACH_WORKFLOW=false`, restart backend. No migration to revert.

### Reporting & Dashboards

#### `FEATURE_REPORT_BUILDER`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** custom report builder, scheduled report emails
- **Rollback:** Set `FEATURE_REPORT_BUILDER=false`, restart backend. No migration to revert.

#### `FEATURE_DASHBOARD_BUILDER`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** custom dashboard widget builder
- **Rollback:** Set `FEATURE_DASHBOARD_BUILDER=false`, restart backend. No migration to revert.

### Access Control & Security

#### `FEATURE_TEAM_ACCESS`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** team-based data isolation, territory management
- **Rollback:** Set `FEATURE_TEAM_ACCESS=false`, restart backend. No migration to revert.

#### `FEATURE_FIELD_PERMISSIONS`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** per-field role-based visibility rules
- **Rollback:** Set `FEATURE_FIELD_PERMISSIONS=false`, restart backend. No migration to revert.

#### `FEATURE_SESSION_MANAGEMENT`

- **Default:** `false`
- **Depends on:** REDIS_URL
- **Required by:** concurrent session limiting, session revocation
- **Rollback:** Set `FEATURE_SESSION_MANAGEMENT=false`, restart backend. No migration to revert.

### Integrations & API

#### `FEATURE_WEBHOOKS`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** outgoing webhook dispatch, webhook log UI
- **Rollback:** Set `FEATURE_WEBHOOKS=false`, restart backend. No migration to revert.

#### `FEATURE_PUBLIC_API`

- **Default:** `false`
- **Depends on:** DATABASE_URL, JWT_SECRET_KEY
- **Required by:** external REST API access, API key management
- **Rollback:** Set `FEATURE_PUBLIC_API=false`, restart backend. No migration to revert.

### Product & Configuration

#### `FEATURE_PRODUCT_RULES`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** product compatibility rules, bundle validation
- **Rollback:** Set `FEATURE_PRODUCT_RULES=false`, restart backend. No migration to revert.

#### `FEATURE_CUSTOM_FIELDS`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** user-defined entity fields, custom field rendering
- **Rollback:** Set `FEATURE_CUSTOM_FIELDS=false`, restart backend. No migration to revert.

### Progressive Web App

#### `FEATURE_PWA`

- **Default:** `false`
- **Depends on:** CORS_ORIGINS
- **Required by:** offline mode, push notifications, install prompt
- **Rollback:** Set `FEATURE_PWA=false`, restart backend. No migration to revert.

### Campaigns

#### `FEATURE_CAMPAIGNS`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** campaign list/detail pages, ROI tracking
- **Rollback:** Set `FEATURE_CAMPAIGNS=false`, restart backend. No migration to revert.

### Invoicing

#### `FEATURE_INVOICING`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** invoice list/detail, PDF generation, billing workflow
- **Rollback:** Set `FEATURE_INVOICING=false`, restart backend. No migration to revert.

### E-Signature

#### `FEATURE_ESIGN`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** document signing workflow, public signing page
- **Rollback:** Set `FEATURE_ESIGN=false`, restart backend. No migration to revert.

### Multi-Pipeline

#### `FEATURE_MULTI_PIPELINE`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** pipeline list/CRUD, pipeline_id on opportunities
- **Rollback:** Set `FEATURE_MULTI_PIPELINE=false`, restart backend. No migration to revert.

### Territory Management

#### `FEATURE_TERRITORIES`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** territory CRUD, user assignments, auto-assign, territory_id on customers/opportunities
- **Rollback:** Set `FEATURE_TERRITORIES=false`, restart backend. No migration to revert.

### Revenue Recognition

#### `FEATURE_REV_REC`

- **Default:** `false`
- **Depends on:** DATABASE_URL, contracts
- **Required by:** revenue schedule CRUD, monthly entry generation, recognition workflow, dashboard
- **Rollback:** Set `FEATURE_REV_REC=false`, restart backend. No migration to revert.

### Live Chat

#### `FEATURE_LIVE_CHAT`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** visitor session creation, agent assignment, message history, auto-response rules
- **Rollback:** Set `FEATURE_LIVE_CHAT=false`, restart backend. No migration to revert.

### Sequences V2 (Cadence Engine)

#### `FEATURE_SEQUENCES_V2`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** idempotent step execution, global exit conditions, step run telemetry,
- **Rollback:** Set `FEATURE_SEQUENCES_V2=false`, restart backend. No migration to revert.

### Behavioral Scoring

#### `FEATURE_BEHAVIORAL_SCORING`

- **Default:** `false`
- **Depends on:** DATABASE_URL, FEATURE_SEQUENCES_V2
- **Required by:** lead/opportunity dynamic scoring from engagement signals,
- **Rollback:** Set `FEATURE_BEHAVIORAL_SCORING=false`, restart backend. No migration to revert.

### Buyer Relationship Map

#### `FEATURE_BUYER_MAP`

- **Default:** `false`
- **Depends on:** DATABASE_URL
- **Required by:** stakeholder CRUD on opportunity/customer, buying committee visualization,
- **Rollback:** Set `FEATURE_BUYER_MAP=false`, restart backend. No migration to revert.

## Enabling a flag — checklist

1. Verify each `Depends on:` entry is satisfied — env var set, related flag enabled, migration applied.
2. In staging: set the flag, restart, exercise the feature manually and via load test.
3. If staging is clean for ≥48h, enable in prod via Render dashboard env vars.
4. Watch Sentry, BetterStack, and `/api/health` for regressions.
5. If something breaks: flip back to `false`, restart. There's no data to roll back.
