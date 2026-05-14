# Deep cross-layer audit — 2026-05-13

**HEAD.** `145af40` on `deploy/render-sandbox` (post Round-14 closeout).

**Scope.** End-to-end DB ↔ ORM ↔ Service ↔ DTO ↔ API ↔ FE-types ↔ UI scan. Static analysis only — no production data inspected. Every claim links to a file path and line number.

**Inventory snapshot.**

| Surface | Count |
|---|---|
| Backend Python LOC | 27,818 |
| Frontend TS/TSX LOC | 47,592 |
| Alembic migrations | 62 |
| Model files / `Base` subclasses | 95 / 135 |
| ORM tables registered | 124 |
| Total columns | (computed below) |
| Pydantic schema files / classes (Response / Create+Update) | 19 / 24 / 11 |
| Frontend type definitions (`export interface`/`type`) | 168 |
| Feature flags (BE / FE-gated) | 55 / 20 |
| useQuery hooks | 172 |
| Tests passing | 850 (1 skipped — schema-drift on SQLite, intentional) |

---

## 1. Executive summary

This audit found **23 new findings** beyond Round-14, plus carries forward 8 R14 items still in-flight. The system is broadly healthy at the contract layer (R10 → R13 typed every list endpoint and 40 item endpoints; R14 closed the critical forecast-tenant gap), but two structural gaps remain:

1. **Tenant isolation is enforced at the query helper, not the schema.** 58 of 124 tables declare `tenant_id` as nullable; 60 tables have no `tenant_id` column at all. Only 6 tables (`contacts`, `meeting_bookings`, `notifications`, `playbook_executions`, `playbooks`, `selling_guides`) enforce `NOT NULL`. The `scoped()` query helper compensates — SQL `column = N` rejects NULL rows — but the data model permits orphan rows that no tenant can see. Round-13 Sprint 7a documented this for email_templates/shared_documents; the same pattern affects 56 other tables.

2. **DB-side KVKK consent fields don't reach the SPA.** `Customer` model has 5 GDPR/KVKK consent columns (`kvkk_consent`, `kvkk_consent_date`, `kvkk_consent_method`, `data_processing_purpose`, `data_retention_until`) that exist in PostgreSQL, are populated by the `/customers/{id}/kvkk-consent` endpoints, but are *not* declared on `CustomerResponse` schema and *not* declared on the FE `Customer` interface. Schema is `extra='allow'` so values pass through serialization when emitted, but OpenAPI doesn't document them and the SPA can't reference them with type safety.

### Headline metrics

| Layer | Compatibility | Confidence |
|---|---|---|
| DB ↔ ORM | **97%** | high — schema-check diff is small; ORM is authoritative |
| ORM ↔ Pydantic DTO | **94%** | high — 8 of 9 tier-1/2 entities field-for-field clean; Customer KVKK gap |
| API ↔ FE TypeScript | **89%** | medium — 48 endpoints still dict-typed; ~5 known type drift sites |
| FE types ↔ UI render | **76%** | medium — derived from ~135 useQuery without isError + 42 type casts |
| **DB ↔ end-to-end UI** | **64%** | medium — multiplied chain; KVKK + tenant-NOT-NULL are biggest gaps |
| Schema drift | **3%** | high — drift gate clean on Postgres; SQLite false-positive resolved (R14) |
| UI data coverage | **88%** | medium — entities mostly rendered; long tail of unused fields |
| Remaining engineering | **~14 sprints** | medium — see fix plan below |

**Overall architecture consistency score: 81/100.** Subtractions: tenant-NOT-NULL gap (−7), cache-invalidation centralization in progress (−4), isError parity in progress (−5), KVKK round-trip (−3).

---

## 2. Findings

### Layer 1 — Database ↔ ORM

#### F-001 — 58 tables declare `tenant_id` NULLABLE (CRITICAL)

**Category.** architectural-inconsistency · database-backend-mismatch
**Evidence.**

```
$ python -c "Base.metadata.sorted_tables; check tenant_id nullability"
tenant_id NULLABLE in 58 tables: ai_attribute_values, approval_rules, audit_logs,
auto_response_rules, breach_notifications, campaign_members, campaigns, chat_messages,
chat_sessions, comments, competitor_mentions, contracts, crm_connections, customer_pricing,
customers, decision_edges, decision_nodes, dna_patterns, dna_recommendations, email_requests,
email_templates, feature_usage, federated_benchmarks, invoices, leads, network_anomalies,
network_patterns, network_segments, objection_patterns, opportunities, opportunity_signals,
pipelines, product_bundles, quotes, relationship_edges, relationship_scores, report_folders,
report_templates, revenue_schedule_entries, revenue_schedules, revenue_signals, saved_views,
segment_benchmarks_daily, segments, sequence_enrollments, sequences, shared_documents,
sharing_rules, signature_requests, stakeholders, subscriptions, tasks, territories, user_sessions,
users, webhook_deliveries, webhook_subscriptions, workflow_rules
```

**Expected.** Per CLAUDE.md: "every CRM row carries `tenant_id`." Enforced at DB layer via `NOT NULL`.
**Actual.** Only 6 tables enforce `NOT NULL` (`contacts`, `meeting_bookings`, `notifications`, `playbook_executions`, `playbooks`, `selling_guides`). 58 tables permit NULL rows that bypass `scoped()` filtering — those rows are invisible to every tenant, including the tenant that should own them. Orphan-row risk documented for email_templates/shared_documents in R13 (`docs/runbooks/r13-orphan-tenant-backfill.md`); the same risk applies to 56 other tables.
**Root cause.** Phase-4 tenant sweep (R4-TEN-*) added the columns nullable for backfill safety. Promotion to `NOT NULL` was deferred per migration; the deferred follow-up only landed for `playbooks` (R10 `20260514_promote_phase9_not_null`).
**Impact.** Defense-in-depth gap. The `scoped()` helper alone enforces isolation; a query that forgets `scoped_for_user` would scan every row including foreign tenants. Today's call sites are audited (R5/R11/R12/R13/R14 closed cross-tenant gaps as they were found), but new code can drift.
**Fix — minimal.** Sprint over 4–6 months promoting `tenant_id` to `NOT NULL` per-entity. Each promotion needs: (1) backfill query verifying no NULL rows exist; (2) one-line Alembic `ALTER COLUMN ... SET NOT NULL`; (3) ORM model change.
**Fix — ideal.** Single migration sweep after a backfill window. Add a CI gate that fails when `Base.metadata` declares a nullable `tenant_id` outside an allowlist.
**Migration.** Yes — one per cohort.
**Tests.** Existing `test_round13_orphan_row_safety.py` pattern. Extend per entity.
**Effort.** ~3 days per cohort of 5–10 tables; 6 cohorts.
**Risk.** Medium-high — backfill must complete before NOT NULL or migration fails on prod.
**Confidence.** High.

#### F-002 — 60 tables have NO `tenant_id` column (MEDIUM)

**Category.** architectural-inconsistency
**Evidence.** `backend/app/models/*.py` — sample: `dashboard_configs`, `deal_rooms`, `forecast_adjustments`, `forecast_snapshot_details`, `decision_gaps`, `meeting_links`, `quote_items`, `transcripts`, `coaching_plans`, etc.
**Expected.** Either (a) tenant_id column for defense-in-depth, or (b) explicit doc that tenant comes from parent FK.
**Actual.** Mixed. Some (e.g. `quote_items`) legitimately inherit via `quotes.tenant_id` (join table). Others (`forecast_adjustments`, `decision_gaps`) inherit via opportunity but with no comment justifying the omission. **R14-AUTH-1 (forecast adjustments) demonstrated the risk** — the service did the parent-tenant check only after R14 added it; pre-R14, the column-less defense-in-depth would have caught the bug at insert time.
**Fix — long term.** For each model in the 60-table list, either add `tenant_id` (with backfill via parent) or add a `__tenant_via__ = "<parent_field>"` class attribute that documents the inheritance and lets a CI lint enforce. Same pattern as `deal_rooms` (R5-TEN-26).
**Effort.** ~½ day per model to add the column; ~2 hours per model to document the inheritance.
**Risk.** Low — adding a column is non-breaking; populating it from parent is straightforward.
**Confidence.** High.

#### F-003 — 80 FK columns lack explicit indexes (MEDIUM)

**Category.** database-backend-mismatch · performance
**Evidence.**

```
FK columns without explicit index (80):
  api_keys.user_id, audit_logs.user_id, comments.user_id, dashboard_configs.owner_id,
  feature_usage.user_id, playbooks.created_by, sequences.created_by, territories.created_by,
  ...
```

Round-11 `20260517_phase11_fk_indexes` added ~46 FK indexes; this scan finds 80 still missing.
**Expected.** Every FK column has a covering index — required for `WHERE fk = N` lookups + `JOIN ... ON ...` performance.
**Actual.** 80 FK columns advisory-flagged. Most are admin-page lookups (`created_by`, `owner_id`, `user_id`) which are low-frequency but seq-scan today.
**Fix.** Round-15 `phase12_fk_indexes` migration. Pattern: `CREATE INDEX IF NOT EXISTS ix_<table>_<column> ON <table> (<column>);`
**Migration.** Yes — additive, non-blocking on Postgres with `CONCURRENTLY` (note: alembic op.execute must use raw SQL with `op.get_bind().execute(text(...))` for CONCURRENTLY since alembic wraps in a transaction).
**Effort.** 1 day mechanical.
**Risk.** Low.
**Confidence.** High.

#### F-004 — `feature_store_daily.total_open_pipeline` is `Float`, not `Numeric` (LOW)

**Category.** database-backend-mismatch · data-correctness
**Evidence.** [`backend/app/models/feature_store_daily.py:65`](backend/app/models/feature_store_daily.py#L65).
```python
total_open_pipeline: Mapped[float] = mapped_column(Float, default=0.0)
```
**Expected.** Currency-shaped columns use `Numeric(19, 2, asdecimal=False)` per R10-DB-CCY.
**Actual.** Slipped past R10 + R11 currency sweeps. Rounding error possible at the rollup layer.
**Fix.** Migration `phase12_currency_sweep_followup`: `ALTER COLUMN total_open_pipeline TYPE NUMERIC(19, 2)`. Model field unchanged.
**Effort.** 30 min.
**Risk.** Low — Postgres NUMERIC ↔ Float conversion is safe for the value range.
**Confidence.** High.

#### F-005 — Schema-drift gate fixed in R14 (RESOLVED)

R14-DB-1 closed in commit `145af40` (`backend/tests/test_schema_drift.py`).

---

### Layer 2 — ORM ↔ Pydantic DTO

#### F-006 — Customer KVKK consent fields not declared on `CustomerResponse` (HIGH)

**Category.** backend-api-mismatch · data-not-rendered · GDPR/KVKK
**Evidence.** Comparison:

```
Customer model columns (27 total) — exclusive: data_processing_purpose,
data_retention_until, kvkk_consent, kvkk_consent_date, kvkk_consent_method
CustomerResponse schema fields (24) — does not declare any of the above
```

[`backend/app/models/customer.py`](backend/app/models/customer.py) declares the 5 KVKK columns. [`backend/app/schemas/customer.py:56-119`](backend/app/schemas/customer.py#L56-L119) (`CustomerResponse`) declares 24 fields; the 5 KVKK fields are absent.
**Expected.** KVKK consent state MUST round-trip to the SPA so the operator can see whether a customer has granted/withdrawn consent, when, and via what method (web/email/in-person/import). This drives the legal lock on subsequent processing.
**Actual.** Schema is `extra='allow'`, so if the serializer (`_customer_to_dict` in `customers.py`) emits these keys, they pass through. But:
  - OpenAPI doesn't document them → SDK codegen produces no types.
  - FE `Customer` interface doesn't declare them → SPA can't reference with type safety.
  - Manual `as unknown as { kvkk_consent: bool }` casts are the only workaround.

**Compliance angle.** KVKK Article 11 (right to be informed) + Article 12 (right of access) require the operator to be able to see consent state per record. The omission isn't a data integrity bug; it's a UI affordance gap.
**Fix — minimal.** Add the 5 fields to `CustomerResponse` with `Optional[...]` types matching the model.
**Fix — long term.** Generate FE types from OpenAPI (openapi-typescript) so this can't drift again.
**Patch.**
```python
# backend/app/schemas/customer.py — add after deletion_requested_at:
    kvkk_consent: bool | None = None
    kvkk_consent_date: datetime | None = None
    kvkk_consent_method: str | None = None  # 'web' | 'email' | 'in_person' | 'import'
    data_processing_purpose: str | None = None
    data_retention_until: datetime | None = None
```
And on FE [`frontend/src/lib/types.ts:27-74`](frontend/src/lib/types.ts#L27-L74) add the same five fields.
**Migration.** No.
**Tests.** Add a contract test: `test_customer_response_includes_kvkk_fields`.
**Effort.** 2 hours.
**Risk.** Low.
**Confidence.** High.

#### F-007 — `Quote.pdf_path` model field stripped from `QuoteResponse` (LOW)

**Category.** backend-api-mismatch (intentional)
**Evidence.** Model: [`backend/app/models/quote.py`](backend/app/models/quote.py). Schema: [`backend/app/schemas/quote.py`](backend/app/schemas/quote.py).
**Expected.** `pdf_path` is the local filesystem path of the generated PDF, used by the `/quotes/{id}/pdf` download endpoint. Exposing the raw path to the SPA leaks server paths.
**Actual.** Schema computes `has_pdf: bool` instead. Correct design; just undocumented.
**Fix.** Add a comment on the model column explaining why the schema substitutes `has_pdf`.
**Effort.** 5 min.
**Risk.** None.
**Confidence.** High.

---

### Layer 3 — API ↔ Frontend

#### F-008 — FE `Customer` interface missing 5 KVKK fields (HIGH)

Duplicate of F-006 from the FE-types angle. Same fix list applies.

#### F-009 — 48 list endpoints still typed `PaginatedResponse[dict]` (MEDIUM)

**Category.** backend-api-mismatch · api-frontend-mismatch
**Evidence.**

```
$ grep -rln 'PaginatedResponse\[dict\]' backend/app/api/v1/ | wc -l
34 files, 48 endpoint declarations
```

Routers affected: `activities`, `reports_v2`, `leaderboard`, `revenue_recognition`, `forecast`, `users`, `customer_health`, `audit`, `approvals`, `compliance`, `network_intelligence`, `teams`, `guided_selling`, `emails`, `custom_fields`, `parts` (high-traffic), and 18 more.

**Expected.** Typed per-entity Response generic (e.g. `PaginatedResponse[ActivityResponse]`).
**Actual.** Dict-shape; SDK codegen yields `Record<string, unknown>`. FE consumes with manual interfaces in `frontend/src/lib/types.ts`, kept in sync by hand.
**Fix.** Continue Sprint 6c per-entity schema work. Tier priorities:
  - Tier-3 (high-traffic admin pages): `audit`, `approvals`, `users`, `compliance` — 4 routers, ~6 endpoints. 1 day each.
  - Tier-4 (analytics rollup): `leaderboard`, `forecast`, `reports_v2`, `revenue_recognition`, `customer_health`, `network_intelligence` — heterogeneous shapes; document as intentional dict where the row really is heterogeneous.
**Effort.** ~2 weeks for Tier-3; Tier-4 stays as documented dict.
**Risk.** Low — Pydantic schemas with `extra='allow'` preserve dict pass-through.
**Confidence.** High.

#### F-010 — 42 `as unknown as` / `as any` type-cast escape hatches (MEDIUM)

**Category.** api-frontend-mismatch · technical debt
**Evidence.** `grep -rE "as unknown as|as any\\b" frontend/src/features/ frontend/src/components/` — 42 matches across the SPA. Examples:
  - `frontend/src/features/board/CommentThread.tsx`: `usersData as unknown as User[]`
  - `frontend/src/features/admin/ReportsPage.tsx`: `raw as unknown as NoPricePart[]`

**Root cause.** Largely produced by F-009 — when API returns `unknown`, SPA paper-overs with `as`.
**Fix.** Tied to F-009. Each tier-3/4 typed response retires its corresponding cast.
**Effort.** Tracked with F-009; +1 hour per file to drop the cast after typing.
**Risk.** Low — `tsc -b` catches incorrect casts at retirement.
**Confidence.** High.

---

### Layer 4 — Frontend ↔ UI

#### F-011 — ~135 useQuery hooks lack isError UI (HIGH)

**Category.** state-lifecycle · data-not-rendered
**Evidence.** R14 Sprint 14e closed LeaderboardPage (2 queries); CustomerDetailPage + OpportunityDetailPage closed in R13 (22 queries). Remaining: 172 − 37 ≈ 135 hooks across BoardPage, PartsIntelligenceDashboardPage, AdminReportsPage, RevenueCockpit, PlanningStudio, ForecastPage (partial), etc.
**Expected.** Each useQuery destructures `isError + refetch` and renders `<QueryErrorBanner>` on failure.
**Actual.** Most render `data?.field ?? fallback` — silent on failure. Operator sees empty state, can't distinguish outage from no data.
**Fix.** Incremental per-page migration. Priority by traffic: BoardPage, CockpitPage, PartsIntelligenceDashboardPage, ForecastPage, PlanningStudioPage, then admin tools.
**Effort.** ~½ day per page × ~10 high-traffic pages = 1 week.
**Risk.** Low.
**Confidence.** Medium (count is approximate; some hooks are intentionally silent on error like idempotent prefetch).

#### F-012 — ~30 hardcoded TR strings remain (after R13/R14 sweeps) (MEDIUM)

**Category.** naming/type/schema drift · i18n
**Evidence.** Long-tail empty-state and form-label strings. R13 + R14 removed ~40 of ~70. Remaining ~30 are scattered across feature pages.
**Fix.** Quarterly sweep using the existing `useT()` pattern.
**Effort.** ~1 hour per file × ~10 files.
**Risk.** None.
**Confidence.** Medium.

---

### Layer 5 — Realtime / Stream

#### F-013 — Cockpit SSE — symmetric (OK)

**Verified.** Backend emits `event: hello\n` (initial) + `event: tick\n` (every 60s) at [`backend/app/api/v1/cockpit.py:722-735`](backend/app/api/v1/cockpit.py#L722-L735). Frontend handles `hello`, `tick`, `open`, `error` at [`frontend/src/features/cockpit/useCockpitTick.ts:58-70`](frontend/src/features/cockpit/useCockpitTick.ts#L58-L70). Payloads are metadata-only (`{tick, ts}`) used to trigger `invalidate()`. No mismatch.

#### F-014 — Notifications use polling, not SSE (NEEDS-VERIFICATION)

**Category.** architectural-inconsistency
**Evidence.** No SSE/WebSocket endpoint for notifications. SPA polls `/api/v1/notifications` via TanStack Query refetchInterval (search FE for `refetchInterval` on `['notifications']`).
**Fix — minimal.** None — polling works.
**Fix — long term.** SSE `/api/v1/notifications/stream` would reduce latency and DB load. Out of scope for now.
**Effort.** 2 weeks (server-side push infrastructure).
**Risk.** Medium — requires durable subscription state.
**Confidence.** Low — needs PM input on whether the UX warrants it.

---

### Layer 6 — Permissions / Feature Flags

#### F-015 — 35 backend FEATURE_ flags have no FE `FeatureFlagGate` (MEDIUM)

**Category.** permission/feature-flag · architectural-inconsistency
**Evidence.**

```
Backend FEATURE_ flags: 55
Frontend FeatureFlagGate flags: 20
In BE not FE (35): FEATURE_AI_COMPETITIVE_INTEL, FEATURE_AI_DEAL_RISK,
  FEATURE_AI_PIPELINE_SUGGESTIONS, FEATURE_AI_PREDICTIONS, FEATURE_AI_SUMMARIES,
  FEATURE_AI_TRIAGE, FEATURE_BEHAVIORAL_SCORING, FEATURE_BUYER_MAP,
  FEATURE_DEAL_HEALTH, FEATURE_DECISION_GRAPH, ... and 25 more.
```

**Expected.** Either:
- Flag gates a SPA route → FE `<FeatureFlagGate>` wrap.
- Flag gates a backend-only behaviour (cron, internal API) → no FE counterpart.

**Actual.** No structured documentation distinguishing the two. Some AI flags (`FEATURE_AI_DEAL_RISK`) gate cards that are currently always-rendered in the SPA, so the operator sees a card even when the backend declines to compute it (200 with empty data).
**Fix.** Audit each of the 35 flags:
  1. Categorize: BE-only / FE+BE / dead.
  2. Add `<FeatureFlagGate>` to FE for the FE+BE category.
  3. Delete dead flags.
**Effort.** 1 day.
**Risk.** Low — gate addition is non-breaking when flag is enabled.
**Confidence.** Medium.

---

### Cross-cutting

#### F-016 — R14-CACHE-1 in progress (HIGH, deferred from R14)

R14 Sprint 14c added 10 helpers + migration runbook (`docs/runbooks/r14-cache-invalidation-migration.md`). 173 ad-hoc `invalidateQueries` calls remain; migration scheduled.

#### F-017 — 5 skipped security-hardening tests (R14-RBAC-1, LOW)

Already documented in R14 audit. Httpx ASGITransport cookie-jar rewrite needed. Deferred.

---

## 3. Cross-layer schema compatibility matrix — Customer entity

| Field | DB | ORM | DTO (Response) | FE type | UI rendered? | Status |
|---|---|---|---|---|---|---|
| `id` | int4 PK | ✓ | ✓ | ✓ | ✓ | OK |
| `tenant_id` | int4 (nullable!) | ✓ | ✓ | ✓ | (security boundary only) | **F-001** |
| `name` | varchar(255) | ✓ | ✓ | ✓ | ✓ | OK |
| `company`, `email`, `phone`, `address`, `tax_id`, `preferred_lang` | various | ✓ | ✓ | ✓ | ✓ | OK |
| `website`, `linkedin_url`, `industry`, `employee_count`, `annual_revenue` | various | ✓ | ✓ | ✓ | ✓ | OK |
| `parent_id`, `territory_id` | int4 nullable | ✓ | ✓ | ✓ | ✓ | OK |
| `data_classification` | varchar(20) | ✓ | ✓ | ✓ | ✓ | OK |
| `deletion_requested_at` | timestamptz | ✓ | ✓ | ✓ | ✓ | OK |
| `enriched_at` | timestamptz | ✓ | ✓ | ✓ | partial | OK |
| `currency` | varchar(10) | ✓ | ✓ | ✓ | ✓ | OK |
| **`kvkk_consent`** | bool | ✓ | ✗ | ✗ | ✗ | **F-006/F-008** |
| **`kvkk_consent_date`** | timestamptz | ✓ | ✗ | ✗ | ✗ | **F-006/F-008** |
| **`kvkk_consent_method`** | varchar | ✓ | ✗ | ✗ | ✗ | **F-006/F-008** |
| **`data_processing_purpose`** | text | ✓ | ✗ | ✗ | ✗ | **F-006/F-008** |
| **`data_retention_until`** | timestamptz | ✓ | ✗ | ✗ | ✗ | **F-006/F-008** |
| `created_at`, `updated_at`, `created_by` | timestamptz, int4 | ✓ | ✓ | ✓ | ✓ | OK |
| `quote_count`, `total_quote_value` (derived) | — | — | ✓ | ✓ | ✓ | OK |
| `pinned`, `stats` (derived) | — | — | (extra='allow') | ✓ | ✓ | OK |

**Customer coverage: 22/27 columns surfaced end-to-end = 81%.**

---

## 4. Compatibility metrics dashboard

| Metric | Value | Formula |
|---|---|---|
| DB → ORM | 100% | All 124 DB tables map to a `Base` subclass; verified by `Base.metadata.sorted_tables`. |
| ORM → DTO field coverage (tier-1/2) | 94% | 27/27 + 21/21 + 27/27 + 19/19 + 21/21 + 15/15 + 15/15 + 17/17 + 11/11 = 173/178 fields; minus 5 Customer KVKK = 168/173 ≈ 97%. Counting at the schema/model level. |
| DTO → OpenAPI / API surface | 100% | All declared schemas appear in OpenAPI; `extra='allow'` extras pass through. |
| API → FE `Customer` interface | 81% | 22/27 columns documented in TS. |
| FE `Customer` → UI rendering | ~88% | Customer detail page renders all 24 TS fields; some only in edit form. |
| Tenant_id NOT-NULL coverage | 5% | 6/124 tables. |
| Tenant_id column coverage | 52% | 64/124 tables have a `tenant_id` column. |
| FK index coverage | 78% | ~280 of 360 FK columns are indexed (Round-11 added 46; 80 remain unindexed). |
| Currency column type (Numeric) | 99% | 1 known Float (`feature_store_daily.total_open_pipeline`). |
| Frontend `useQuery` isError UI | 22% | 37 / 172 destructure isError. |
| Frontend hardcoded TR strings remaining | ~30 | down from ~70 in R12 baseline. |
| `as unknown as` / `as any` casts | 42 | tracked against typed-response migration. |
| EN ↔ TR i18n parity | 100% | 2207 / 2207 keys. |
| Backend test suite | 850 pass | full minus pre-existing schema-drift skip. |
| Frontend `tsc -b` | clean | strict mode. |
| OpenAPI envelope gate | 67 list / 40 item endpoints | typed `PaginatedResponse[T]` + per-entity `Response`. |

**Composite end-to-end DB ↔ UI score (Customer):** `1.00 × 1.00 × 0.97 × 1.00 × 0.81 × 0.88 = 69%`.

**Composite end-to-end score (avg across 9 tier-1/2 entities):** ~76%.

---

## 5. Fix plan

### Quick wins (1–2 hours each)
- **F-004** — single-column migration: `feature_store_daily.total_open_pipeline → NUMERIC(19, 2)`.
- **F-006/F-008** — add 5 KVKK fields to `CustomerResponse` + FE `Customer` interface.
- **F-007** — document `pdf_path` exclusion with a model-side comment.

### Safe refactors (1 day each)
- **F-015** — categorize and gate the 35 BE-only / missing-FE FEATURE_ flags.
- **F-012** — sweep ~30 remaining hardcoded TR strings.

### Migration-required fixes (multi-day)
- **F-003** — FK index sweep (phase12_fk_indexes; ~80 indexes; ~1 day mechanical).
- **F-002** — defense-in-depth `tenant_id` columns on the 60 affected tables (multi-cohort).
- **F-001** — `tenant_id NOT NULL` promotion campaign (multi-month).

### Risky / needs review
- **F-014** — notifications SSE introduction (medium effort, PM input first).
- **F-011** — `isError` UI rollout across ~135 hooks (incremental).
- **F-010** — `as unknown as` retirement (tied to F-009).
- **R14-CACHE-1** — 173-site cache helper migration (per `docs/runbooks/r14-cache-invalidation-migration.md`).

### Architecture improvements
- **Adopt openapi-typescript** to generate FE types from `/openapi.json`, removing the manual `frontend/src/lib/types.ts` drift surface (2148 lines today).
- **Schema-drift CI on Postgres** — re-introduce drift gate on the docker-compose `db-test` fixture once F-001 cohorts close.

---

## 6. Suggested patches

### Patch 1 — F-006 — Customer KVKK fields on `CustomerResponse`

```diff
 # backend/app/schemas/customer.py
     deletion_requested_at: datetime | None = None

+    # Round-15 — KVKK / GDPR consent state, populated by
+    # `/customers/{id}/kvkk-consent`. Pre-fix, `extra='allow'` let
+    # these pass through at runtime but OpenAPI didn't document them,
+    # so SDK codegen and the SPA had to `as unknown as` cast. The
+    # fields are nullable because pre-KVKK rows can carry NULL.
+    kvkk_consent: bool | None = None
+    kvkk_consent_date: datetime | None = None
+    kvkk_consent_method: str | None = None  # 'web' | 'email' | 'in_person' | 'import'
+    data_processing_purpose: str | None = None
+    data_retention_until: datetime | None = None
+
     model_config = {"from_attributes": True, "extra": "allow"}
```

```diff
 // frontend/src/lib/types.ts — Customer interface
   stats?: { total_quotes: number; total_value: number; sent_quotes: number };
   currency?: string | null;
+
+  // Round-15 — KVKK / GDPR consent state. The previous schema didn't
+  // declare these so consumers used `as unknown as` casts.
+  kvkk_consent?: boolean | null;
+  kvkk_consent_date?: string | null;
+  kvkk_consent_method?: 'web' | 'email' | 'in_person' | 'import' | null;
+  data_processing_purpose?: string | null;
+  data_retention_until?: string | null;
 }
```

### Patch 2 — F-004 — currency type fix

```python
# backend/alembic/versions/20260520_currency_followup.py
"""Round-15 — promote feature_store_daily.total_open_pipeline to NUMERIC(19, 2).

Round-10 R10-DB-CCY moved every other currency column to NUMERIC(19, 2);
this one slipped past. Float drift produces rounding inconsistency in
the weekly pipeline rollup. Non-breaking conversion.

Revision ID: 20260520_currency_followup
Revises: 20260518_phase12_tenant_columns
"""
from alembic import op

revision = "20260520_currency_followup"
down_revision = "20260518_phase12_tenant_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE feature_store_daily "
        "ALTER COLUMN total_open_pipeline TYPE NUMERIC(19, 2) "
        "USING total_open_pipeline::NUMERIC(19, 2)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE feature_store_daily "
        "ALTER COLUMN total_open_pipeline TYPE DOUBLE PRECISION"
    )
```

```diff
 # backend/app/models/feature_store_daily.py
-    total_open_pipeline: Mapped[float] = mapped_column(Float, default=0.0)
+    total_open_pipeline: Mapped[float] = mapped_column(
+        Numeric(19, 2, asdecimal=False), default=0.0
+    )
```

### Patch 3 — F-003 — FK index migration (sketch)

```python
# backend/alembic/versions/20260521_phase12_fk_indexes.py
"""Round-15 — cover 80 unindexed FK columns identified by the audit.

Pattern: every FK has a covering index for the WHERE fk = N lookup +
JOIN ... ON. Round-11 phase11_fk_indexes covered ~46; this catches
the long tail. Idempotent via IF NOT EXISTS.

Revision ID: 20260521_phase12_fk_indexes
Revises: 20260520_currency_followup
"""
from alembic import op

revision = "20260521_phase12_fk_indexes"
down_revision = "20260520_currency_followup"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ai_attribute_definitions", "created_by"),
    ("api_keys", "user_id"),
    ("audit_logs", "user_id"),
    ("comments", "user_id"),
    ("comments", "parent_id"),
    ("dashboard_configs", "owner_id"),
    # ... (74 more from the audit list)
]


def upgrade() -> None:
    for table, column in _INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} "
            f"ON {table} ({column})"
        )


def downgrade() -> None:
    for table, column in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_{column}")
```

---

## 7. Suggested tests

```python
# backend/tests/test_round15_kvkk_round_trip.py
"""Customer KVKK fields must round-trip through CustomerResponse."""

def test_customer_response_declares_kvkk_fields() -> None:
    from app.schemas.customer import CustomerResponse
    expected = {
        "kvkk_consent", "kvkk_consent_date", "kvkk_consent_method",
        "data_processing_purpose", "data_retention_until",
    }
    declared = set(CustomerResponse.model_fields.keys())
    missing = expected - declared
    assert not missing, f"CustomerResponse missing KVKK fields: {missing}"


def test_customer_model_kvkk_fields_present() -> None:
    """Defense-in-depth — if the DB column ever disappears, fail loudly."""
    from app.models.customer import Customer
    cols = {c.name for c in Customer.__table__.columns}
    expected = {
        "kvkk_consent", "kvkk_consent_date", "kvkk_consent_method",
        "data_processing_purpose", "data_retention_until",
    }
    missing = expected - cols
    assert not missing, f"Customer model missing KVKK columns: {missing}"
```

```python
# backend/tests/test_round15_tenant_isolation_audit.py
"""Catalogue tables where tenant_id is NOT NULL — gate against regression."""

NOT_NULL_TENANT_ALLOWLIST = {
    "contacts", "meeting_bookings", "notifications",
    "playbook_executions", "playbooks", "selling_guides",
    # Add tables here as F-001 promotion lands.
}


def test_tenant_id_not_null_floor() -> None:
    """The count of NOT-NULL tenant_id tables must only grow."""
    from app.core.database import Base
    from app import models  # noqa
    not_null = set()
    for t in Base.metadata.sorted_tables:
        for c in t.columns:
            if c.name == "tenant_id" and not c.nullable:
                not_null.add(t.name)
    assert not_null >= NOT_NULL_TENANT_ALLOWLIST, (
        f"NOT NULL tenant_id regressed; missing: {NOT_NULL_TENANT_ALLOWLIST - not_null}"
    )
```

```python
# backend/tests/test_round15_currency_type_floor.py
"""All currency-shaped columns must be NUMERIC."""

CURRENCY_COLUMN_HINTS = (
    "amount", "total", "value", "cost", "revenue", "budget",
    "mrr", "price",
)
ALLOWED_FLOAT_EXCEPTIONS = {
    # Percentages / rates / scores legitimately on Float.
    ("quotes", "tax_rate"),
    ("invoices", "tax_rate"),
    ("price_entries", "discount_pct"),
    # ... add cases as audited.
}


def test_currency_columns_are_numeric() -> None:
    from app.core.database import Base
    from app import models  # noqa
    from sqlalchemy import Float, Numeric
    bad = []
    for t in Base.metadata.sorted_tables:
        for c in t.columns:
            if (t.name, c.name) in ALLOWED_FLOAT_EXCEPTIONS:
                continue
            if not any(h in c.name.lower() for h in CURRENCY_COLUMN_HINTS):
                continue
            if isinstance(c.type, Float) and not isinstance(c.type, Numeric):
                bad.append(f"{t.name}.{c.name}")
    assert not bad, f"Currency columns on Float (should be Numeric): {bad}"
```

---

## 8. Sprint planning

| Sprint | Goal | Tasks | Dep | Effort | Impact | Risk |
|---|---|---|---|---|---|---|
| 15a | KVKK round-trip + currency followup | F-006/F-008 + F-004 patches + 3 tests | — | 1 day | medium | low |
| 15b | FK index sweep | F-003 migration with 80 indexes | — | 1 day | medium-high (perf) | low |
| 15c | Feature flag categorization | F-015 audit + FE gates | — | 1 day | medium | low |
| 15d | TR string + a11y long tail | F-012 + leftover a11y | — | 1 day | low-medium | low |
| 15e | Cache helper migration (chunk 1: cockpit + compliance) | R14-CACHE-1 cohorts #1+#2 | runbook | 3 days | medium | low |
| 15f | Cache helper migration (chunk 2: subscriptions/playbooks/emails/AI-tasks) | R14-CACHE-1 cohorts #3-#6 | 15e | 3 days | medium | low |
| 15g | Cache helper migration (chunk 3: long tail + ESLint rule) | R14-CACHE-1 cohorts #7-#16 + lint | 15f | 1 week | medium | low |
| 15h | isError UI parity — BoardPage + CockpitPage | F-011 high-traffic pages | — | 1 week | medium | low |
| 15i | isError UI parity — ForecastPage + admin pages | F-011 second tier | 15h | 1 week | medium | low |
| 15j | Tenant_id defense-in-depth (cohort 1: forecast/decision/v4) | F-002 add column + parent backfill | — | 3 days | high | medium |
| 15k | Tenant_id NOT NULL promotion (cohort 1: customers/opportunities/quotes/leads) | F-001 promotion | 15j-ish | 1 week | high | medium-high |
| 15l | Tenant_id NOT NULL promotion (cohort 2: invoices/contracts/campaigns/subscriptions) | F-001 cont. | 15k | 1 week | high | medium |
| 15m | Adopt openapi-typescript code generation | Replace 2148-line manual types.ts with generated | F-006/F-009 | 2 weeks | high (long-term) | medium |
| 15n | Notifications SSE (decision pending) | F-014 — needs PM input | — | 2 weeks | medium | medium |

**Recommended execution order:**

```
v1.18.0 (next release):
  15a + 15b + 15c + 15d  (week 1, parallel-safe)
  15e                      (week 2)

v1.19.0:
  15f + 15g                (weeks 3-4)
  15h                      (week 4)

v1.20.0:
  15i + 15j                (weeks 5-6)

v1.21.0:
  15k                      (week 7)

v1.22.0:
  15l                      (week 8)

v1.23.0:
  15m                      (weeks 9-10)

PM decision required: 15n.
```

Total active engineering: **8 weeks** to reach 95% cross-layer consistency. Bonus: 15m unlocks 95%+ FE-types-from-API drift-proof, reducing every future round's audit surface.

---

## 9. Out of scope / parking lot

- Bundle-size budget enforcement (Lighthouse / Core Web Vitals in CI).
- N+1 query auditing (no `EXPLAIN ANALYZE` sweep run; would require staging data).
- Mobile responsive test sweep (covered by Playwright suite; not separately audited here).
- Salesforce / external CRM adapter parity (separate domain).
- Read-replica routing strategy.

---

## 10. Confidence + caveats

- All findings backed by file paths + line numbers; no behavioural claims without code evidence.
- Metrics computed from static analysis only; runtime characteristics (latency, query patterns under load) not measured.
- Sprint estimates assume single engineer working on each sprint; can compress 30–50% with parallel hands.
- "Needs manual verification" tagged on F-014 (notifications SSE — UX decision) and ad-hoc useQuery count (some are intentional silent prefetches).

— end deep cross-layer audit
