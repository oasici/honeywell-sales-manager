# V3 Platform Expansion — Roadmap

Feature parity push against Rapitek, Salesforce, MS Dynamics, HubSpot and Zoho.
Mobile work is intentionally excluded and tracked separately.

## Branch

`feature/v3-platform-expansion` — based on `deploy/render-sandbox` (Sprint 0-8 complete).

## Progress

### Sprint 1 — Foundations (done)

- `app/core/crypto.py` shared Fernet helper with MultiFernet rotation support.
- `app/models/erp.py` + Alembic migration `20260422_add_erp_connector_tables`
  (connections, mappings, sync jobs, conflicts).
- `app/services/erp/` package:
  - `base.py` — `ERPConnector` Protocol + DTOs.
  - `mapping_engine.py` — field translator, payload hashing, diff helpers.
  - `conflict_resolver.py` — LWW policy + conflict persistence.
  - `orchestrator.py` — Redis-lock aware sync runner.
  - `factory.py` — dispatches on connection type.
  - `adapters/parasut.py` — full OAuth2 + REST implementation.
  - `adapters/logo.py` — Logo Tiger / Netsis XML-RPC skeleton.
  - `adapters/sap_b1.py` — v1.1 placeholder.
  - `adapters/webhook.py` — inbound-only adapter.
- `app/services/ai_trust.py` — PII scrubber (email, phone, TCKN, VKN, IBAN, card).
- `claude_parser.py` scrubs prompts + unscrubs responses when
  `FEATURE_AI_TRUST_LAYER` is on (default true).
- Config flags:
  - `FEATURE_ERP_CONNECTOR`, `FEATURE_AI_TRUST_LAYER`
  - `FEATURE_FIELD_AUDIT` + `FIELD_AUDIT_RETENTION_DAYS=3650`
  - `FEATURE_WHATSAPP`, `FEATURE_CONVERSATION_INTEL`,
    `FEATURE_AGENTIC_SDR`, `FEATURE_MARKETPLACE`
- Tests: `tests/test_ai_trust.py`, `tests/test_erp_mapping.py` (14 passing).

### Sprint 2 — API + Admin UI (done skeleton)

- `app/api/v1/erp.py` — 12 endpoints (connections CRUD, test, sync, jobs,
  mappings, conflicts, credentials probe).
- `app/schemas/erp.py` — request/response contracts.
- Router registration in `app/api/v1/router.py`.
- Frontend `erpApi` with full type coverage in `src/lib/api.ts`.
- `features/admin/erp/ERPConnectionsPage.tsx` — list + create wizard +
  Trust Layer explainer.
- `features/admin/erp/ERPConnectionDetailPage.tsx` — jobs / mappings /
  conflicts tabs with inline resolution.
- Lazy routes `/admin/erp` and `/admin/erp/:id`, sidebar nav
  `nav.erp_connector` across 5 locales (tr/en/de/fr/es).

## Pending (ordered)

### Sprint 3 — Logo hardening + mapping UI depth

1. Logo Tiger partner sandbox validation (cookbook of real method names).
2. Per-entity field mapping UI with drag-drop overrides persisted to
   `ERPConnection.config_json`.
3. Bulk conflict resolver actions.

### Sprint 4 — Event bus + quote→invoice

1. Domain events `erp.customer.synced`, `erp.stock.changed` wired into
   playbook/signal pipelines.
2. Quote-to-invoice push button on `QuoteDetailPage` (Paraşüt).
3. Scheduler integration (APScheduler cron from `sync_cron`).
4. Grafana metrics + E2E Playwright coverage.

### Parallel tracks

- **Field Audit Trail** — new `field_audit_log` model + decorator applied to
  ORM `before_update` events; retention from `FIELD_AUDIT_RETENTION_DAYS`.
- **WhatsApp Business** — `app/services/whatsapp/` package, inbound webhook
  `/integrations/whatsapp/webhook`, template message sender.

### Later (tracked)

- Conversation intelligence (uploaded transcript summarization only).
- Operations / MRP module (BOM, warehouses, barcode).
- Agentic SDR agent built on Claude tool-use + event bus.
- Marketplace / plugin sandbox on top of existing webhook infrastructure.
- SOC 2 Type I evidence package (policies, audit trails, access controls).

## Local verification checklist

```bash
# backend
cd backend && source venv/bin/activate
python -m pytest tests/test_ai_trust.py tests/test_erp_mapping.py -q
python -c "from app.api.v1.router import v1_router; print(len(v1_router.routes))"

# frontend
cd ../frontend
npx tsc --noEmit
```

Alembic upgrade (once env has `DATABASE_URL`):

```bash
cd backend && source venv/bin/activate
alembic upgrade head
```

## Feature flag matrix

| Flag                        | Default | Gates                                   |
|-----------------------------|---------|-----------------------------------------|
| FEATURE_ERP_CONNECTOR       | false   | `/api/v1/erp/*`, orchestrator, UI nav   |
| FEATURE_AI_TRUST_LAYER      | true    | Claude parser PII scrub + audit log     |
| FEATURE_FIELD_AUDIT         | false   | ORM field diff capture + long retention |
| FEATURE_WHATSAPP            | false   | outbound templates + inbound webhook    |
| FEATURE_CONVERSATION_INTEL  | false   | transcript upload + Claude summary      |
| FEATURE_AGENTIC_SDR         | false   | autonomous follow-up agent              |
| FEATURE_MARKETPLACE         | false   | plugin sandbox / tenant webhooks        |
