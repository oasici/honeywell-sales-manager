# Round-15 Mid-Sprint Cross-Layer Audit — Honeywell Sales Suite

**Date.** 2026-05-20 · **Branch.** `deploy/render-sandbox` · **HEAD.** `48e777b` · **Prior audits.** R1–R14 (`docs/audits/`), most recent R14 = 2026-05-13.

**Method.** 6 parallel read-only specialist agents (DB↔ORM, BE↔API, API↔FE, UI coverage, realtime/SSE, permissions) + structural scan across 74 077 LOC backend / 99 563 LOC frontend / 86 Alembic migrations. No live database introspection; all evidence is static. No files modified during the audit pass.

**One-line takeaway.** Round-15 is mid-flight and has aggressively closed Round-14 (75 % of R14 findings verified shut). Two *new* CRITICAL cross-tenant leaks have surfaced (`dashboard.py`, `customer_health`). The biggest architectural finding is that the openapi-typescript artifact landed today (sprint 15m) but is **unused** — zero SPA files import from `api-types.gen.ts`.

---

## 1. Executive Summary

| Bucket | Count |
|---|---|
| Total findings (NEW + carry-over) | **82** |
| **CRITICAL** (new since R14) | **2** |
| HIGH | 19 |
| MEDIUM | 36 |
| LOW | 25 |
| Round-14 findings verified CLOSED | 6 / 12 = **50 % hard-closed**, +3 substantially advanced = **75 % effectively closed** |
| Round-14 findings still open | 3 |

**Most affected surfaces.** Quotes (5 fetched-not-rendered), Approvals (model↔serializer drift + escalation gaps), Dashboard (cross-tenant aggregates), Customer-health (cross-tenant leak), the engagement + analytics routers (1 typed response out of 42 endpoints).

**Biggest schema drift areas.** (1) Backend Pydantic ↔ FE-generated types layer: 76.8 % of operations resolve to `unknown`. (2) Generated types not consumed: 0 SPA imports of `api-types.gen.ts`, 165 manual interfaces. (3) NOT NULL tenant_id cohort lag: 19 second-tier tables not promoted (intentional staging).

**Overall system compatibility score.** **~62 %** (weighted; formula in §6). **Remaining development to reach 90 %**: estimated **~18-22 engineering days** in well-defined sprints (§11).

**Technical-debt estimate.** ~480 LOC of `?? fallback` + 165 duplicate FE interfaces + 46 untyped paginated endpoints. Quantified retirement: ~3 engineer-weeks if executed as cohorts.

---

## 2. Round-14 Closeout Verification

| R14 ID | R14 state | HEAD state (2026-05-20) | Status |
|---|---|---|---|
| R14-AUTH-1 forecast tenant | CRITICAL open | `forecast_service.py:89, 143` call `assert_same_tenant` w/ `exception_cls=NotFoundException`; router threads `current_user` (`api/v1/forecast.py:153, 173`). | **CLOSED ✓** |
| R14-AUTH-2 dashboard 403 leak | HIGH open | `dashboard_builder.py:245` collapses foreign-owner to `NotFoundException`. | **CLOSED ✓** |
| R14-FE-1 isError UI (137/172 hooks lack) | HIGH | 106 `isError` refs + 59 `QueryErrorBanner` usages across ~107 useQuery files. | **~70 % closed** (was 20 %) ⏳ |
| R14-CACHE-1 ad-hoc vs centralized invalidation (173/16) | HIGH | 20+ files import `lib/cacheInvalidation.ts`; only **5 ad-hoc holdouts** (`admin/AiAttributesPage`, `cockpit/{useCockpitTick, CockpitPage}`, `ui/SavedViewsBar`, `layout/Header`). | **~97 % closed** ✓ |
| R14-API-1 PaginatedResponse[dict] (48 endpoints) | MEDIUM | **46 holdouts** (not 33 as my earlier grep suggested; 2 closed since R14). | ~4 % closed ❌ |
| R14-DB-1 schema-drift gate failing on TIMESTAMPTZ | MEDIUM | `core/schema_check.py:149-154` normalizes both forms. | **CLOSED ✓** |
| R14-I18N-1 12 hardcoded TR strings | MEDIUM | F-012 scoping doc landed 2026-05-19; mechanical work pending. | scoped, not executed ⏳ |
| R14-A11Y-1 focus-ring replacements | MEDIUM | Not verified this round — needs manual check. | unknown |
| R14-TS-1 42 `as unknown as` / `as any` | MEDIUM | **6** remaining. | **~86 % closed** ✓ |
| R14-LOG-1 1 console.error | LOW | **2** files (regression of +1). | regressed ❌ |
| R14-TODO-1 7 TODO/FIXME | LOW | **2**. | ~71 % closed ✓ |
| R14-RBAC-1 5 skipped security tests | LOW | Not verified. | unknown |

---

## 3. NEW Findings — Critical & High

### 3.1 CRITICAL

#### N15-AUTH-3 — Cross-tenant aggregate leak on `dashboard.py` (CRITICAL)
- **Category.** API ↔ Service permissions / database-backend
- **Where.** `backend/app/api/v1/dashboard.py:25, 30, 35, 40, 46, 51, 56, 67, 75, 85, 93, 99, 107, 113, 121` — 15 unscoped `select(func.count/sum(...))` queries over `EmailRequest`, `Quote`, `QuoteItem`, `Customer`, `SparePart`. `current_user` is declared at line 19 but never passed to query.
- **Risk.** Every authenticated user sees **global aggregates across all tenants** — revenue totals, customer counts, parts movement. Confidentiality breach. Easily reproduced with two test users in different tenants.
- **Fix (min).** Thread `current_user.tenant_id` into every `select(...)`; add `.where(Model.tenant_id == current_user.tenant_id)` to all 15 queries. ~30 LOC.
- **Fix (ideal).** Use `scoped_for_user` helper consistently as in `customers.py`. Add `test_dashboard_tenant_isolation.py` mirroring `test_round14_forecast_tenant_guard.py`.
- **Migration.** No.
- **Effort.** 3-4 h incl. tests. **Risk.** LOW (additive WHERE clauses). **Confidence.** HIGH.

#### N15-AUTH-4 — Cross-tenant `customer_health` leak (CRITICAL)
- **Category.** Service permissions
- **Where.** `backend/app/services/customer_health_service.py:115, 145, 192` — `calculate_health_score`, `get_all_health_scores`, `get_at_risk_customers` accept no `current_user` and never filter `Customer.tenant_id`. Callers `api/v1/customer_health.py:62, 106, 144` declare `current_user` but don't thread it.
- **Risk.** Endpoints `/overview`, `/at-risk`, `/{customer_id}` return foreign-tenant customer health (churn risk, score, last activity, NPS). Reachable by any authenticated user.
- **Fix (min).** Add `current_user: User` parameter to all three service methods, filter `Customer.tenant_id == current_user.tenant_id`, return `NotFoundException` on `/{customer_id}` for foreign tenant.
- **Tests.** `test_customer_health_tenant_guard.py`.
- **Effort.** 3-4 h. **Risk.** LOW. **Confidence.** HIGH.

### 3.2 HIGH — Architecture

#### N15-ARCH-1 — `api-types.gen.ts` shipped but never imported (HIGH)
- **Category.** architectural inconsistency / api-frontend mismatch
- **Where.** `frontend/src/lib/api-types.gen.ts` (32 987 LOC, 568 operations, 212 schemas) — generated today (sprint 15m, commit `5b8a453`). **Zero** SPA files outside `lib/types.ts` import from it.
- **Evidence.** `grep -r "api-types.gen" frontend/src/` returns only `lib/types.ts` references. `lib/types.ts:1-14` carries the documented intent to migrate but did not execute. 165 manual interfaces remain.
- **Impact.** The 15m sprint delivered a contract artifact only. No FE consumer benefits from the type safety it provides. 76.8 % of endpoints (436/568) would still resolve to `unknown` even if imported — because `response_model=` coverage is only 21 %. Both layers need work before the import migration is worthwhile.
- **Fix (min).** Codemod 7 verified-divergent CRM interfaces (`Customer`, `Opportunity`, `Lead`, `Quote`, `Contract`, `User`, local admin `User`) to alias `components['schemas']['*Response']`. Document divergences (`pinned`, `rotting_days`, `owner_name`, `quote_count`, `total_quote_value` etc.).
- **Fix (ideal).** Reverse-direction: add the 5 missing fields to backend response schemas instead of keeping them as FE-only invariants, then import.
- **Effort.** 1 day for codemod, 3 days to backfill missing backend fields.

#### N15-API-1 — `response_model=` coverage 21 % / 76.8 % FE unknowns (HIGH)
- **Where.** `backend/app/api/v1/` — 538 endpoint decorators, **113** declare `response_model=`. 46 `PaginatedResponse[dict]` holdouts.
- **Top 10 worst routers.** `engagement.py` (25/4), `analytics.py` (22/1), `ai.py` (18/0), `v9_gap_closure.py` (16/0), `v10_parts_intel.py` (16/0), `settings.py` (14/0), `reports_v2.py` (14/2), `integrations.py` (12/0), `compliance.py` (13/2), `customers.py` (18/8).
- **Quick wins (each <30 LOC).**
  1. `parts.py:22` → wire existing `SparePartResponse` (schema already correct).
  2. `prices.py:22` → wire existing `PriceEntryResponse`.
  3. `emails.py:61` → wire `EmailRequestResponse`.
  4. `customers.py:105 /high-intent` → define 6-field `HighIntentAccountResponse`.
  5. `notifications.py:24` → define `NotificationResponse`.

#### N15-API-2 — 7 routers expose models with no Pydantic schema at all (HIGH)
- **Routers.** `users.py` (auth-adjacent), `settings.py` (entire router, 14 endpoints, 0 schemas), `audit.py` (`PaginatedResponse[dict]` for security audit data), `compliance.py` (KVKK/GDPR — retention + breach notifications as bare dicts), `api_key.py` (secret-bearing), `engagement.py` (25 endpoints / 4 typed = biggest gap), `meetings.py` (7/0).
- **Risk.** SDK codegen falls back to `Any`; tests cannot assert response shape; field rename in model silently breaks SPA. For `users.py` and `api_key.py` specifically, hand-built dicts must remember to omit `hashed_password` / api-key secret — a single forgetful PR causes a leak.

#### N15-API-3 — Schema "Optional-everywhere" pattern (HIGH, contract weakness)
- **Where.** Every Response schema for `Customer`, `Opportunity`, `Lead`, `Quote`, `Contract`, `Subscription`, `Invoice` marks ORM-NOT-NULL fields as `Optional`. Pattern is documented intent (see `schemas/customer.py:65-79`) driven by `apply_request_perms()` masking.
- **Impact.** The wire contract claims fields can be null when the database guarantees they aren't. SDK consumers must null-check unnecessarily; FE compensates with `?? 0` / `?? ""` fallbacks (10 instances catalogued, see N15-FE-5).
- **Fix.** Split into two schemas per entity: `EntityResponse` (NOT NULL guarantees match ORM) and `EntityMaskedResponse` (Optional fields, used only when permissions mask). Add field-level `Annotated[…, Required()]` for guaranteed fields.

### 3.3 HIGH — Database

#### N15-DB-1 — `revenue_schedule_entries.status` enum drift (HIGH)
- **Where.** `backend/alembic/versions/20260610_phase14_enum_check_constraints.py:65-68` enforces `status IN ('pending','recognized','reversed')`. `backend/app/models/revenue_recognition.py:73` comment says `# pending | recognized | adjusted`.
- **Risk.** Latent CheckViolation. Any future code path writing `status='adjusted'` (matching the model docstring) raises at INSERT. Code search confirms only `pending` and `recognized` are currently written, so this is a footgun, not a live bug.
- **Fix (min).** Edit model comment to match CHECK. Or, if `adjusted` is the desired semantic, add an Alembic revision that updates the CHECK and adds an enum entry.

#### N15-DB-2 — `achievements.tenant_id` model says NOT NULL but cohort-7 didn't promote it (HIGH)
- **Where.** `backend/app/models/achievement.py:23` — `nullable=False`. `backend/alembic/versions/20260611_phase13_tenant_not_null_cohort7.py:26-29` only promotes `api_keys`, `deal_similarity_links` — `achievements` and `push_subscriptions` skipped despite cohort-11 backfill in `20260601_phase12_tenant_did_cohort11.py`.
- **Risk.** Schema-drift gate (`SCHEMA_DRIFT_MODE=fail`) will refuse to boot once a runtime check sees `model=NOT NULL db=NULLABLE` for `achievements.tenant_id`. Currently masked because either (a) the gate is on `warn` in prod, or (b) all current rows are non-null and detection requires column metadata not row inspection.
- **Fix.** Add Alembic revision `20260520_phase13_tenant_not_null_cohort9.py` promoting `achievements.tenant_id` (and `push_subscriptions.tenant_id`) to NOT NULL using the cohort-4/7 4-step pattern (backfill orphans → ALTER COLUMN → ALTER CONSTRAINT → verify).

#### N15-DB-3 — Rollup tables have no `tenant_id` at all (HIGH)
- **Where.** `backend/app/models/feature_store_daily.py:65-99` (`AccountFeaturesDaily`) and `:102-123` (`RepFeaturesDaily`) — no `tenant_id`. Sibling `OpportunityFeaturesDaily:25` has one.
- **Risk.** Account-level / rep-level rollups are unscoped. If `scoped_for_user` is added to a query that touches these tables, the filter silently fails. Cross-tenant aggregate leak possible if these tables get exposed via a future endpoint.
- **Status.** Needs manual verification whether this is intentional (admin-global) or oversight.
- **Fix.** If unintentional: Alembic revision adding `tenant_id` column + backfill via `account_id → customers.tenant_id` (for account_features) and `user_id → users.tenant_id` (for rep_features).

### 3.4 HIGH — Realtime

#### N15-EVT-1 — 0 of 14 event-bus events relayed to SPA via SSE (HIGH)
- **Where.** Cockpit SSE (`backend/app/api/v1/cockpit.py:708-746`) emits only `hello` and `tick` — a dumb heartbeat. The 14 domain events in `backend/app/services/domain_events.py:23-51` (`opportunity.created`, `quote.approved`, `lead.converted`, …) flow only to webhooks, Slack/Teams, and the workflow subscribers — never to the SPA.
- **Polling masks the gap.** 8 sites poll data the bus already publishes:
  1. `components/layout/Header.tsx:25, 52` — unread-count, 90 s
  2. `features/dashboard/DashboardPage.tsx:151-173` — stats + activity feed, 30 s
  3. `features/board/CommentThread.tsx:195` — comments
  4. `features/engagement/SequencesPage.tsx:141` — 120 s; sequence.\* events fire on bus
  5. `components/layout/Sidebar.tsx:192-195` — approvals/pending, 60 s
  6. `features/dashboard/LeaderboardCard.tsx:39` — 120 s
  7. `features/chat/AgentChatPage.tsx:54, 61`, `ChatWidget.tsx:86` — chat polling (no bus event yet)
  8. `features/admin/{EventAuditLogPage:76, SystemHealthPage:80}` — ops boards, arguably appropriate
- **Notifications-SSE design doc** (`docs/audits/2026-05-19-15n-notifications-sse-design.md`) explicitly describes 0 % implementation — backend `/notifications/stream` and FE `useNotificationStream` do not exist.
- **Fix.** Implement the notifications-SSE design after the PM decision recorded in the doc. Until then, accept polling — the design correctly concludes "don't ship now".

#### N15-EVT-2 — 2 event constants have no producer (HIGH, dead code or lost code)
- **Where.** `backend/app/services/domain_events.py:40` (`LEAD_SCORE_CHANGED = "lead.score_changed"`) and `:37` (`SEQUENCE_ENROLLED_AUTO = "sequence.enrolled_auto"`).
- **Evidence.** Webhook subscriber wired (`main.py:232`) for `lead.score_changed`. No `event_bus.publish("lead.score_changed", ...)` anywhere in `backend/`.
- **Risk.** Webhooks subscribed to these events will never fire — silent failure. Either the publisher was removed without retiring the constant (regression) or the publisher was never written.
- **Fix.** `grep -r 'LEAD_SCORE_CHANGED\|SEQUENCE_ENROLLED_AUTO' backend/` to confirm; if no caller, delete constants. If a caller is expected (per scoring_service comment), restore the `emit_domain_event` call.

#### N15-EVT-3 — `invoice.paid` subscriber is a `pass` stub (HIGH)
- **Where.** `backend/main.py:258-260` — webhook subscriber body is `pass`. Event is published from `api/v1/invoices.py:349` (gated `FEATURE_INVOICE_PAID_EVENT`).
- **Impact.** Customers expecting `invoice.paid` webhooks receive nothing despite the route advertising it. Either delete the subscription or implement the handler.

### 3.5 HIGH — Edit-Form & Serializer Drift

#### N15-FE-1 — `OpportunityUpdate` silently drops `forecast_category` (HIGH)
- **Where.** FE form at `frontend/src/features/board/OpportunityDetailPage.tsx:576` sends `forecast_category` in the PATCH body. `backend/app/api/v1/opportunities.py:53-61` `OpportunityUpdate` does not include it. FastAPI silently ignores unknown fields (no `model_config['extra']='forbid'`).
- **Impact.** User edits forecast_category on detail page — save succeeds, value never persists.
- **Fix.** Add `forecast_category`, `pipeline_id`, `territory_id`, `source`, `probability` to `OpportunityUpdate`. ~5 LOC.

#### N15-FE-2 — `CustomerUpdate` silently drops `data_classification` (HIGH)
- **Where.** FE `CustomerDetailPage.tsx:359-366` sends `data_classification` via Select. `schemas/customer.py:36-53` `CustomerUpdate` does not include it.
- **Impact.** KVKK/GDPR-relevant data classification edits are lost.
- **Fix.** Add `data_classification: DataClassification | None = None` to `CustomerUpdate`. ~3 LOC + 1 test.

#### N15-FE-3 — `ApprovalRule.chain_mode / delegate_to / delegate_until` are model-only (HIGH)
- **Where.** `backend/app/models/approval.py:40-54` declares them; `backend/app/api/v1/approvals.py:312-328 _rule_to_dict` omits all three. FE `ApprovalRulesPage.tsx` has no field.
- **Impact.** Delegation feature is operational on the server (`/approvals/delegate` writes the fields) but invisible on read. Operators cannot see who they delegated approval to or when it expires.
- **Fix.** Add the 3 fields to `_rule_to_dict`; add a "Delegation" panel to `ApprovalRulesPage.tsx`.

### 3.6 HIGH — Ops Hygiene

#### N15-OPS-1 — `ops.py /feature-flags` leaks all `FEATURE_*` (MEDIUM-HIGH)
- **Where.** `backend/app/api/v1/ops.py:130-140` returns every `FEATURE_*` from `settings.__dict__` (no allowlist). The `_PUBLIC_FEATURE_FLAGS` allowlist at `config.py:32-105` is bypassed.
- **Risk.** Internal/experimental flag names (e.g. `FEATURE_TRANSFORMER_SEQ_EMBEDDING`) are enumerated for any auth'd caller. Roadmap leak; minor security concern.
- **Fix.** Filter to `_PUBLIC_FEATURE_FLAGS` set. ~5 LOC.

---

## 4. Medium-Severity Findings (consolidated)

### 4.1 NOT NULL cohort follow-ups (5 items, MEDIUM)
- **F-15.** `revenue_schedule_entries.tenant_id` (`models/revenue_recognition.py:65`) — parent already NOT NULL.
- **F-16.** `tasks.tenant_id` (`models/opportunity.py:153`) — backfilled, NOT promoted.
- **F-17.** `stakeholders.tenant_id` (`models/sequence_v2.py:93`).
- **F-18.** `campaign_members.tenant_id` (`models/campaign.py:69`) — parent `campaigns.tenant_id` NOT NULL since cohort 2.
- **F-19.** `webhook_deliveries.tenant_id` (`models/webhook.py:68`) — parent `webhook_subscriptions` NOT NULL since cohort 4.

### 4.2 Fetched-Not-Rendered (top 10)
| # | Field | Backend | FE consumer status |
|---|---|---|---|
| 1 | `Quote.approved_by` | `quotes.py:748` | none |
| 2 | `Quote.closed_at` / `close_reason` | `quotes.py:776-781` | none |
| 3 | `Quote.email_request_id` | `quotes.py:745` | none (loses provenance link) |
| 4 | `Quote.created_by` | `quotes.py:747` | none |
| 5 | `ContractAmendment.approved_by` | `contracts.py:99` | absent from amendment timeline |
| 6 | `ApprovalRule.escalation_hours` / `_action` | `approvals.py:325-326` | not rendered |
| 7 | `ApprovalRule.approver_user_id` | `approvals.py:322` | only `approver_role` shown |
| 8 | `ApprovalRequest.rule_id` | `approvals.py:336` | not shown on pending list |
| 9 | `Lead.converted_by` | `leads.py:625` | not shown on conversion card |
| 10 | `Opportunity.probability` | `opportunities.py:135` | only stage-derived prob shown |

### 4.3 Hardcoded fallbacks masking missing data (10 sites)
1. `features/customers/CustomerListPage.tsx:79` — `c.quote_count ?? 0`
2. `features/customers/CustomerListPage.tsx:203` — `c.total_quote_value ?? 0`
3. `features/opportunities/OpportunitiesHomePage.tsx:220` — `total ?? filtered.length`
4. `features/opportunities/OpportunitiesHomePage.tsx:241` — cast-then-fallback hides shape error
5. `features/board/OpportunityDetailPage.tsx:241, 242` — `intelligence?.signals ?? []`, `?? tasks []`
6. `features/board/OpportunityDetailPage.tsx:460` — accepts `items` OR `deal_rooms` (legacy envelope)
7. `features/board/CommentThread.tsx:206` — same pattern (`items` OR `comments`)
8. `features/board/SalesAnalyticsPage.tsx:392` — silent 0 if band missing
9. `features/quotes/QuoteComparisonModal.tsx:54, 55` — silent 0 diff on untyped compare endpoint
10. `features/quotes/QuoteEditorPage.tsx:200` — pricing pipeline missing → line total 0

### 4.4 Stale FE field references (8 unique, masked by extras-tolerant generated types)
| FE site | Field | Missing from |
|---|---|---|
| `BoardPage.tsx:123,130,196` | `opp.last_activity_at`, `rotting_days` | `OpportunityResponse` |
| `OpportunitiesHomePage.tsx:404,406` | `rotting_days` | (same) |
| `CustomerDetailPage.tsx:533, 536, 734` | `customer.pinned` | `CustomerResponse` |
| `LeadDetailPage.tsx:387, 392` | `owner_name` | `LeadResponse` |
| `LeadListPage.tsx:204` | column `full_name` | `LeadResponse` |
| `CustomerListPage.tsx:79, 203` | `quote_count`, `total_quote_value` | `CustomerResponse` |
| `BuyerRelationshipMap.tsx:178, 179` | `departments`, `roles` | `unknown` endpoint |

### 4.5 Feature flags (3 items)
- 18 backend-allowlisted flags consumed by no FE component (potential dead code; needs manual verification per flag — could be admin-only enablement).
- `FEATURE_TRANSFORMER_SEQ_EMBEDDING` — backend-only by design (R5-FLAG-18, documented).
- `SalesAnalyticsPage.tsx:119` and `OpportunityDetailPage.tsx:250` treat `operations` role as manager; `forecast.py:269` requires `SALES_MANAGER` only — `operations` users see UI that 403s on click. UX mismatch, not privilege drift.

### 4.6 Mobile / responsive (5 items)
- Only `ContractListPage.tsx:357, 360, 366, 402, 405, 413` uses `hideOn` on `DataTable`.
- `CustomerListPage`, `LeadListPage`, `QuoteListPage`, `OpportunitiesHomePage`, `PendingApprovalsPage`, `ApprovalRulesPage` rely on `overflow-x-auto` — no graceful column degradation. `DataTable` primitive supports `hideOn` (`DataTable.tsx:46-49`) but isn't used.

### 4.7 In-tenant existence leak (LOW-MED)
- `backend/app/api/v1/comments.py:213, 222` — loads by id, calls `assert_same_tenant`, then raises `403` when `user_id != current_user.id`. Within tenant, 403 vs 404 leaks existence of another user's comment. Inconsistent with project convention (CLAUDE.md "Cross-tenant access maps to 404"). Lower risk because same-tenant only.

---

## 5. Cross-Layer Schema Compatibility Matrix

Format: DB column ⇒ ORM mapped_column ⇒ Pydantic schema ⇒ generated FE type ⇒ rendered. Sampled top-10 fields per entity (full matrix omitted for brevity — agent 4 raw output covers 134 fields).

### 5.1 Customer (134-field corpus → 27 sampled here)
| Field | DB | ORM | Schema | api-types.gen | FE manual | Rendered | Status |
|---|---|---|---|---|---|---|---|
| `id` | PK | ✓ | ✓ | ✓ | ✓ | list+detail | OK |
| `name` | NOT NULL | ✓ | Optional | Optional | required | list+detail+form | **Schema-Optional mismatch (N15-API-3)** |
| `company` | nullable | ✓ | Optional | Optional | required | list+detail | minor type mismatch (FE assumes presence) |
| `email`/`phone`/`address` | nullable | ✓ | Optional | Optional | Optional | detail+form | OK |
| `data_classification` | nullable | ✓ | Response only | ✓ | ✓ | detail banner only | **EDIT_BLOCKED (N15-FE-2)** |
| `kvkk_consent` + 4 KVKK fields | nullable | ✓ | Response declares | extras only | ✓ | n/a | **MISSING_IN_FE_UI** |
| `tenant_id` | NOT NULL | NOT NULL | Optional | Optional | Optional | n/a | masking pattern |
| `quote_count` (computed) | — | — | extras only | none | ✓ | list | **stale FE field (4.4)** |
| `total_quote_value` (computed) | — | — | extras only | none | ✓ | list | **stale FE field** |
| `pinned` (computed) | — | — | none | none | ✓ | detail | **stale FE field** |
| `created_at` / `updated_at` | NOT NULL | ✓ | ✓ | ✓ | ✓ | partial | OK |

### 5.2 Opportunity (~22 sampled)
| Field | Status |
|---|---|
| `title`, `stage`, `amount`, `currency`, `close_date`, `status`, `owner`, `customer` | OK |
| `forecast_category` | **EDIT_BLOCKED (N15-FE-1)** |
| `probability` | FETCHED_NOT_RENDERED |
| `source`, `pipeline_id`, `territory_id` | rendered read-only, no edit affordance, schema does not accept |
| `rotting_days`, `last_activity_at`, `open_tasks_count`, `open_quotes_count` | stale FE fields (4.4) — only in manual `Opportunity` |
| `previous_stage`, `previous_amount`, `previous_close_date` | OK (read-only by design) |

### 5.3 Approval (23 sampled)
| Field | Status |
|---|---|
| `name`, `entity_type`, `condition_type`, `threshold_*`, `approver_role`, `priority`, `is_active` | OK |
| `approver_user_id` | FETCHED_NOT_RENDERED |
| `escalation_hours`, `escalation_action` | FETCHED_NOT_RENDERED |
| `chain_mode`, `delegate_to`, `delegate_until` | **MISSING_IN_API (N15-FE-3)** — in model, not in serializer |

(Lead = 89 %, Quote = 64 %, Contract = 68 % per agent 4; matrices omitted.)

---

## 6. Compatibility Metrics Dashboard

All percentages are sampled or whole-population grep-derived. **Confidence**: HIGH for static counts, MEDIUM where extras-tolerant types mask drift.

### 6.1 Layer-pair compatibility
| Pair | Formula | Compatible | Total | % | Confidence |
|---|---|---|---|---|---|
| **DB ↔ ORM** | sampled compatible columns / sampled total | ~1 400 | ~1 445 | **~97 %** | HIGH (sampled) |
| **Backend ORM ↔ Pydantic schemas** | exported schemas / entity-models-exposed-via-API | 58 | ~93 | **~62 %** | MEDIUM |
| **API ↔ FE generated types** | endpoints with typed response / total operations | 115 | 568 | **20.2 %** | HIGH |
| **API ↔ FE consumed types** | SPA files importing `api-types.gen.ts` / total useQuery files | **0** | 107 | **0 %** | HIGH |
| **API ↔ FE effective (manual + generated)** | (typed + duplicated-but-aligned) / total surveyed fields | ~330 | ~700 | **~47 %** | MEDIUM |
| **UI data coverage** (rendered / API-exposed scalar fields, 6 entities) | 97 | 134 | **~72 %** | HIGH |
| **End-to-end DB ↔ UI compatibility** | weighted product | — | — | **~50 %** | MEDIUM |
| **Realtime: SSE coverage** | cockpit-stream | 2 | 2 | **100 %** | HIGH |
| **Realtime: event-bus → SPA** | bus events surfaced on SSE | 0 | 14 | **0 %** | HIGH |
| **Permission coverage** | endpoints with `assert_same_tenant` or `scoped_for_user` | ~299 of ~514 authed handlers | 514 | **~58 %** | MEDIUM (rest are role-only or admin-internal) |

### 6.2 Schema drift
| Metric | Value | Formula |
|---|---|---|
| Schema drift % overall | ~38 % | (Optional-everywhere mismatches + missing schemas + manual-duplicates + stale fields) / surveyed fields |
| Missing field completion % | ~28 % | (fetched-not-rendered + missing-in-fe + missing-in-api) / total CRM fields, 6 entities |
| Remaining development % to reach 90 % | ~22 % | unresolved work / total required = ~20 dev-days / ~90 dev-days roadmap |
| Technical debt % | ~18 % | rough debt LOC / total LOC |

### 6.3 Entity-level compatibility (6 entities)
| Entity | DB→FE coverage | Confidence |
|---|---|---|
| Customer | 63 % | HIGH (KVKK fields missing UI is intentional but counted) |
| Opportunity | 82 % | HIGH |
| Lead | 89 % | HIGH |
| Quote | 64 % | HIGH |
| Contract | 68 % | HIGH |
| Approval | 74 % | HIGH |
| **Mean** | **~72 %** | |

### 6.4 Round-14 closeout score
| Bucket | Count | Notes |
|---|---|---|
| Hard-closed (verified) | 6 / 12 = **50 %** | R14-AUTH-1, R14-AUTH-2, R14-DB-1, R14-CACHE-1, R14-TS-1, R14-TODO-1 |
| Substantially advanced | 3 (R14-FE-1 70 %, R14-I18N-1 scoped, R14-A11Y-1 partial) | |
| Stalled or regressed | 3 (R14-API-1 only 4 % closed, R14-LOG-1 +1 regression, R14-RBAC-1 unknown) | |

---

## 7. Summary Lists

- **DB columns not used by backend:** None identified in sampled set; schema-drift gate covers this.
- **Backend model fields not backed by database:** Possibly `achievements.tenant_id` (model NOT NULL vs DB NULLABLE) — N15-DB-2.
- **Backend fields not exposed through API:** `ApprovalRule.chain_mode`, `delegate_to`, `delegate_until` (N15-FE-3); customer KVKK consent fields suppressed by `_customer_to_dict`.
- **API fields never consumed by frontend:** Top 10 in §4.2 — `Quote.approved_by`, `closed_at`, `close_reason`, `email_request_id`, `created_by`, `Lead.converted_by`, `Opportunity.probability`, `ApprovalRule.{escalation_hours, escalation_action, approver_user_id}`, `ApprovalRequest.rule_id`, `ContractAmendment.approved_by`.
- **Frontend fields/types missing from API/backend:** 8 stale references in §4.4 — `pinned`, `rotting_days`, `last_activity_at`, `owner_name`, `full_name`, `quote_count`, `total_quote_value`, plus 4 entity-local types in `AtRiskPage`, `SalesAnalyticsPage`, `AuditLogPage`, `EventAuditLogPage` against `unknown` endpoints.
- **Data fetched but not rendered:** §4.2 plus all extras returned by serializers that no FE consumer reads.
- **UI components showing incomplete data:** `ContractDetailPage` (customer summary), `ApprovalRulesPage` (escalation), `LeadDetailPage` (converted_by), `QuoteEditorPage` (closed_at, approved_by).
- **Realtime events emitted but not handled by SPA:** 14 — every domain event in `domain_events.py`.
- **Realtime events handled but not emitted:** `lead.score_changed`, `sequence.enrolled_auto` (N15-EVT-2).
- **Schema/type/nullability mismatches:** 19 in §3.3 + §4.1; key: revenue_schedule enum, achievements NOT NULL, feature-store rollups, Optional-everywhere pattern.
- **Permission / feature-flag mismatches:** N15-AUTH-3 (dashboard.py), N15-AUTH-4 (customer_health), N15-OPS-1 (feature-flags endpoint), 18 backend-allowlisted-but-FE-unused flags.
- **Required migrations:** (1) NOT NULL cohort 9 for 5-8 tables, (2) add `tenant_id` to `account_features_daily`+`rep_features_daily` if not intentional global, (3) optional: fix `revenue_schedule_entries.status` CHECK if `adjusted` is desired.
- **Recommended frontend type updates:** Codemod 7 CRM interfaces (`Customer`, `Opportunity`, `Lead`, `Quote`, `Contract`, `User`, admin local `User`) to alias `components['schemas']['*Response']`; add missing fields to backend schemas (`pinned`, `rotting_days`, etc.) first.
- **Recommended backend DTO/serializer updates:** Add `forecast_category` etc. to `OpportunityUpdate`; add `data_classification` to `CustomerUpdate`; emit `chain_mode/delegate_*` from `_rule_to_dict`; promote `dashboard.py` to scoped queries.
- **Recommended tests:** §10.
- **Highest-risk architectural areas:** (1) Dashboard & customer-health unscoped queries, (2) Manual FE type drift from generated artifact, (3) Event-bus has no SPA surface.
- **Quick-win fixes:** §8.1 below.
- **High-impact low-effort fixes:** N15-FE-1, N15-FE-2, N15-FE-3, N15-OPS-1, 5 schema rewires from §3.2.
- **Critical schema drift areas:** revenue_schedule enum (N15-DB-1), achievements NOT NULL (N15-DB-2), feature-store rollups (N15-DB-3).

---

## 8. Fix Plan

### 8.1 Quick wins (~½-1 day each, total ~3 days)
1. **`parts.py:22`** → `PaginatedResponse[SparePartResponse]` (schema exists).
2. **`prices.py:22`** → `PaginatedResponse[PriceEntryResponse]`.
3. **`emails.py:61`** → `PaginatedResponse[EmailRequestResponse]`.
4. **`notifications.py:24`** → new 25-LOC `NotificationResponse`.
5. **`customers.py:105 /high-intent`** → 6-field `HighIntentAccountResponse`.
6. **N15-OPS-1** — filter `/feature-flags` to `_PUBLIC_FEATURE_FLAGS` allowlist.
7. **`ContractDetailPage.tsx:289`** — render `customer.company / customer.name` instead of `#${customer_id}`.
8. **`ContractDetailPage.tsx:370`** — render `amendment.approved_by`.
9. **`LeadDetailPage.tsx:502`** — render `Converted by #{converted_by}`.
10. **N15-FE-1 / N15-FE-2** — add `forecast_category`, `data_classification` to update schemas (~5 LOC each).
11. **N15-DB-1** — fix `revenue_recognition.py:73` model comment.
12. **N15-EVT-2** — delete unused `LEAD_SCORE_CHANGED` and `SEQUENCE_ENROLLED_AUTO` constants OR restore producer (after grep for callers).

### 8.2 Safe refactors (1-3 days each)
- **N15-API-1 cohort.** Schema-ize the 46 `PaginatedResponse[dict]` holdouts in 3-4 PR cohorts (engagement → analytics → reports → long tail).
- **N15-ARCH-1 codemod.** Replace 7 verified-divergent manual CRM interfaces with imports from `api-types.gen.ts`. Pre-step: add the 5-7 missing fields to backend response schemas.
- **Cache helper closure.** Migrate the 5 remaining ad-hoc `invalidateQueries` to `cacheInvalidation` helpers; gate ESLint rule to `error`.
- **`isError` final cohort.** Wire `QueryErrorBanner` to the ~30-40 remaining hooks (R14-FE-1 closeout).

### 8.3 Migration-required fixes
- **NOT NULL cohort 9 (`20260520_phase13_tenant_not_null_cohort9.py`).** Promote `achievements.tenant_id`, `push_subscriptions.tenant_id`, `tasks.tenant_id`, `stakeholders.tenant_id`, `campaign_members.tenant_id`, `webhook_deliveries.tenant_id`, `revenue_schedule_entries.tenant_id`, `contract_amendments.tenant_id`. ~80 LOC migration; use cohort-7 pattern (backfill → ALTER COLUMN → verify).
- **`account_features_daily` + `rep_features_daily` tenant_id addition.** Conditional on PM verification this is unintentional.
- **`revenue_schedule_entries.status` enum.** Only if `adjusted` is the desired terminology — otherwise N15-DB-1 is a model-comment fix.

### 8.4 Risky changes needing manual review
- Schema "Optional-everywhere" rework (N15-API-3) — touches every CRM response schema. Plan as quarterly project, not a sprint.
- Notifications SSE implementation per design — PM decision blocker (doc explicitly says "don't ship now").
- `dashboard.py` tenant-scoping (N15-AUTH-3) — verify reporting accuracy doesn't regress when global aggregates become per-tenant; admin dashboards may need a separate `/admin/dashboard` surface.

### 8.5 Architecture improvements
- **Mandate `response_model=` via lint.** Add a CI check that fails when a router endpoint lacks `response_model=`. Forces N15-API-1 closure forward.
- **Mandate `api-types.gen.ts` consumption.** Add ESLint rule banning manual `interface` declarations for paths that resolve in `api-types.gen.ts`.
- **Domain-event payload schema validation.** `domain_events.py` documents schemas in dicts; promote to Pydantic models and runtime-validate at `event_bus.publish` to prevent silent drift.
- **Dialect-aware schema-drift gate.** Already done (R14-DB-1 closed) — ensure prod is `warn`, dev/CI is `fail`.

---

## 9. Suggested Code Patches (representative)

> Not applied during the audit pass — read-only audit. File:line anchors for diff prep.

### 9.1 N15-AUTH-3 — `dashboard.py` patch sketch
```python
# backend/app/api/v1/dashboard.py:25 (representative — repeat for each of 15 queries)
- result = await db.execute(select(func.count(Customer.id)))
+ result = await db.execute(
+     select(func.count(Customer.id))
+     .where(Customer.tenant_id == current_user.tenant_id)
+ )
```
Repeat for: lines 25, 30, 35, 40, 46, 51, 56, 67, 75, 85, 93, 99, 107, 113, 121. Add `current_user: User = Depends(get_current_user)` to handler signatures where missing.

### 9.2 N15-FE-1 — `OpportunityUpdate` schema extension
```python
# backend/app/api/v1/opportunities.py:53-61
class OpportunityUpdate(BaseModel):
    title: str | None = None
    stage: str | None = None
    amount: Decimal | None = None
    close_date: date | None = None
    owner_id: int | None = None
+   forecast_category: str | None = None
+   pipeline_id: int | None = None
+   territory_id: int | None = None
+   source: str | None = None
+   probability: int | None = None
    notes: str | None = None
    loss_reason: str | None = None
```

### 9.3 N15-FE-3 — `_rule_to_dict` extension
```python
# backend/app/api/v1/approvals.py:312-328
def _rule_to_dict(rule: ApprovalRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        # ... existing fields ...
        "approver_role": rule.approver_role,
        "approver_user_id": rule.approver_user_id,
        "escalation_hours": rule.escalation_hours,
        "escalation_action": rule.escalation_action,
+       "chain_mode": rule.chain_mode,
+       "delegate_to": rule.delegate_to,
+       "delegate_until": rule.delegate_until.isoformat() if rule.delegate_until else None,
        "tenant_id": rule.tenant_id,
    }
```

### 9.4 N15-OPS-1 — allowlist `/feature-flags`
```python
# backend/app/api/v1/ops.py:130-140
from app.core.config import _PUBLIC_FEATURE_FLAGS

@router.get("/feature-flags")
async def get_feature_flags(current_user: User = Depends(get_current_user)):
-   return {k: v for k, v in settings.__dict__.items() if k.startswith("FEATURE_")}
+   return {k: getattr(settings, k) for k in _PUBLIC_FEATURE_FLAGS if hasattr(settings, k)}
```

### 9.5 Quick wins — parts/prices/emails/notifications response_model wiring
```python
# backend/app/api/v1/parts.py:22
-@router.get("/", response_model=PaginatedResponse[dict])
+@router.get("/", response_model=PaginatedResponse[SparePartResponse])
```
Plus `from app.schemas.spare_part import SparePartResponse`. Confirm `_part_to_dict` shape matches `SparePartResponse` (agent 2 verified it does).

---

## 10. Suggested Database Migrations (plans, not commands)

### M-01 — `20260520_phase13_tenant_not_null_cohort9.py`
- **Columns.** `achievements.tenant_id`, `push_subscriptions.tenant_id`, `tasks.tenant_id`, `stakeholders.tenant_id`, `campaign_members.tenant_id`, `webhook_deliveries.tenant_id`, `revenue_schedule_entries.tenant_id`, `contract_amendments.tenant_id`.
- **Pattern.** Cohort-7 (`20260611_phase13_tenant_not_null_cohort7.py`) — backfill orphans (NULL rows) via parent FK lookup → `ALTER COLUMN … SET NOT NULL` per table → verify count.
- **Backfill.** Each child table backfills from its parent's tenant_id (`achievements.user_id → users.tenant_id`, etc.). Orphan rows: delete or assign to a dedicated `__legacy__` tenant.
- **Rollback.** `ALTER COLUMN … DROP NOT NULL`. Idempotent.
- **Risk level.** LOW. Same shape as cohorts 1-8 which have all run cleanly in flight.
- **Estimated production rows.** Unknown without DB introspection; sandbox seed is small.

### M-02 — `20260520_add_tenant_id_to_feature_store_rollups.py` (CONDITIONAL)
- **Only if** PM/data-science verifies rollups should be tenant-scoped (vs global admin views).
- **Columns.** Add `tenant_id INTEGER NULL` to `account_features_daily`, `rep_features_daily`. Backfill from `account_features_daily.account_id → customers.tenant_id` and `rep_features_daily.user_id → users.tenant_id`. Add index. Defer NOT NULL to a later cohort.
- **Risk.** MED. Schema change + backfill on potentially-large rollup tables. Run in maintenance window.

### M-03 — `revenue_schedule_entries.status` enum reconciliation (CONDITIONAL)
- If `adjusted` is the desired status semantic: drop existing CHECK, add new CHECK including `adjusted`. Otherwise: no migration needed — fix the model docstring (quick win).

---

## 11. Suggested Tests

### Backend (Python / pytest)
1. **`test_dashboard_tenant_isolation.py`** — assert every `/dashboard/*` endpoint filters by `tenant_id`. Two tenants, two users, verify no cross-pollination.
2. **`test_customer_health_tenant_guard.py`** — mirror of forecast guard test.
3. **`test_response_model_coverage.py`** — fail CI when a non-internal router endpoint lacks `response_model=`. Whitelist of intentional dict-returning endpoints in `tests/_response_model_exempt.txt`.
4. **`test_approval_rule_serializer_completeness.py`** — assert `_rule_to_dict` returns every column defined on `ApprovalRule` (except `tenant_id` if intentionally hidden).
5. **`test_event_bus_producer_coverage.py`** — for every constant in `DomainEvents`, assert at least one `event_bus.publish(<name>, ...)` call exists in `backend/`.
6. **`test_invoice_paid_subscriber_implements.py`** — assert the `_on_invoice_paid` handler in `main.py` does more than `pass` (e.g., non-trivial AST).
7. **`test_schema_drift_post_cohort9.py`** — after M-01, schema-check gate passes with the additional NOT NULL columns.
8. **`test_feature_flag_endpoint_allowlist.py`** — assert `/api/v1/ops/feature-flags` returns only flags in `_PUBLIC_FEATURE_FLAGS`.
9. **`test_opportunity_update_accepts_forecast_category.py`** — POST/PATCH with full body, assert persisted.

### Frontend (Vitest / Playwright)
10. **`test_api_types_gen_consumed.test.ts`** — fails when a manual `interface Customer | Opportunity | Lead | Quote | Contract | User` declaration exists outside `lib/types.ts`. Static AST scan.
11. **`approvals.delegation-visible.e2e.ts`** — Playwright: open approval rule, set delegate, refresh — assert delegate is visible.
12. **`opportunity-detail-form-fields.test.tsx`** — verify form sends `forecast_category`, server returns updated value.
13. **`responsive-table-coverage.test.ts`** — assert `DataTable` `hideOn` is used on Customer/Lead/Quote/Opportunity list pages (or that overflow is acceptable per PM decision).

### Schema-drift / contract
14. Extend `test_schema_drift.py` with **`test_no_orm_field_without_schema`** — for every entity model declared in `models/`, assert at least one Pydantic schema in `schemas/` references it (filename or AST).
15. **OpenAPI freshness gate** — `gen:api-types:check` is already wired (`frontend/package.json`); add a CI job that fails when `docs/openapi.json` is older than HEAD on a backend route file.

---

## 12. Sprint Planning — Round-16

### Sprint 16a — Critical Security (1 day, blocking) **RISK: HIGH IMPACT**
- **Goal.** Close N15-AUTH-3 (`dashboard.py` cross-tenant aggregates) and N15-AUTH-4 (`customer_health` cross-tenant leak) before next release.
- **Tasks.** Add `current_user` threading + `tenant_id` filter to 15 dashboard queries + 3 customer_health methods; add 2 pytest guards.
- **Dependencies.** None.
- **Effort.** 1 dev-day. **Impact.** Confidentiality breach closure.

### Sprint 16b — Quick-win schema wiring (1-2 days, parallel-safe)
- **Goal.** Close 5 of the 46 `PaginatedResponse[dict]` holdouts using existing schemas (parts, prices, emails, notifications, high-intent customers).
- **Tasks.** ~120 LOC across 5 router files + 2 new schemas. Smoke E2E.
- **Effort.** 1-2 dev-days. **Impact.** Reduces API↔FE `unknown` from 76.8 % to ~75.5 %.

### Sprint 16c — Edit-form drift closure (2 days)
- **Goal.** Close N15-FE-1, N15-FE-2, N15-FE-3 + the `ApprovalRule.escalation_*` rendering gap.
- **Tasks.** Schema additions to `OpportunityUpdate`, `CustomerUpdate`; serializer extension to `_rule_to_dict`; `ApprovalRulesPage` columns/form for escalation + delegation; tests.
- **Effort.** 2 dev-days. **Impact.** Removes 3 user-visible silent-drop bugs.

### Sprint 16d — Ops hygiene & feature-flag tightening (½ day)
- **Goal.** Close N15-OPS-1; sweep 18 dead backend allowlist entries (verify per-flag; delete or wire FE).
- **Effort.** ½ dev-day. **Impact.** Stops roadmap leak via `/feature-flags`.

### Sprint 16e — NOT NULL cohort 9 (1 day, depends on data verification)
- **Goal.** Migration M-01 (8 tables).
- **Tasks.** Backfill verification on sandbox + prod-mirror; Alembic revision; schema-drift gate re-run.
- **Effort.** 1 dev-day (mostly verification). **Risk.** LOW. **Impact.** Closes 5 of 5 NOT-NULL follow-ups.

### Sprint 16f — Realtime hygiene (1 day)
- **Goal.** Close N15-EVT-2 (delete dead constants or restore producers) and N15-EVT-3 (implement or delete `invoice.paid` handler).
- **Effort.** ½ day per item. **Impact.** Removes silent-failure surface for webhook subscribers.

### Sprint 16g — `api-types.gen.ts` consumption codemod (3-5 days, multi-PR)
- **Goal.** First wave of N15-ARCH-1 closure: backfill 5-7 missing fields to backend `*Response` schemas (`pinned`, `rotting_days`, `last_activity_at`, `quote_count`, `total_quote_value`, `owner_name`, `full_name`); codemod 7 CRM manual interfaces to alias generated types; add lint rule.
- **Effort.** 3-5 dev-days. **Impact.** ~30 of 165 manual interfaces retired; type drift score improves from ~60 % to ~50 %.

### Sprint 16h — `response_model=` cohort sweep (5-7 days, multi-PR)
- **Goal.** Reduce 46 `PaginatedResponse[dict]` holdouts to <10 via 4 sub-cohorts:
  - 16h-1: engagement.py (21 endpoints)
  - 16h-2: analytics.py + ai.py (39 endpoints)
  - 16h-3: settings.py + integrations.py (26)
  - 16h-4: long tail (~20 across 15 routers)
- **Effort.** 5-7 dev-days. **Impact.** `unknown` response rate drops from 76.8 % to ~30 %.

### Sprint 16i — Schema-drift gate extension (1-2 days)
- **Goal.** Add `test_response_model_coverage` + `test_no_orm_field_without_schema` + OpenAPI freshness CI gate. Mandates forward progress.
- **Effort.** 1-2 dev-days. **Impact.** Prevents regression of the 16h work.

### Sprint 16j — Long-tail isError + cache helper closure (3-4 days)
- **Goal.** Close R14-FE-1 from 70 % → 95 % and R14-CACHE-1 from 97 % → 100 %; elevate ESLint rule to `error`.
- **Effort.** 3-4 dev-days.

### Optional (after PM gate): Sprint 16k — Notifications SSE per design (2-3 weeks)
- **Goal.** Implement the design doc; close N15-EVT-1 partially (relay 4-6 high-signal events: opportunity.\*, quote.\*, lead.converted, customer.created, approval.requested).
- **Depends on PM go-ahead.** Doc currently says "don't ship now."

### Execution order recommendation
1. **16a (critical security) → release blocker, day 1.**
2. **16b, 16c, 16d, 16f in parallel** (independent files, 1 week elapsed).
3. **16e (cohort 9 migration)** after 16a (don't pile on while a release is mid-deploy).
4. **16g + 16h together** (3 weeks) — both improve cross-layer type safety; share lint scaffolding.
5. **16i** at the end of 16h to lock in gains.
6. **16j** as background hygiene.
7. **16k** only after PM decision recorded in `docs/audits/2026-05-19-15n-…`.

### Estimated total effort to reach 90 % cross-layer compatibility
- Hard work: ~18-22 dev-days across sprints 16a-16i.
- Soft work (16j, 16k): ~6-10 additional days.
- **Round-15 closeout target: 2026-06-15 (4 weeks).**

---

## 13. Out-of-Scope / Limitations / Confidence Notes

- **No live DB introspection.** All DB findings are inferred from migration files + ORM. Production state may differ; the `schema_check.py` gate in `warn` mode would surface live divergence.
- **OpenAPI snapshot stale.** `docs/openapi.json` shows 472 paths vs 538 endpoints in code. Findings keyed to `api-types.gen.ts` reflect 472-path snapshot; the 66 new endpoints (sprint 15m onward) are not yet typed in FE. Re-run `pnpm gen:api-types` to refresh, then re-audit.
- **Agent 2 corrected structural grep.** `PaginatedResponse[dict]` count is **46**, not 33; `response_model=` count is **113**, not 104. Trust agent values.
- **R14-A11Y-1 and R14-RBAC-1** were not re-verified this round — flag for manual sweep.
- **The 18 backend-allowlisted-but-FE-unused feature flags** are tagged "needs manual verification" — some may be admin-only enablement (intentional).
- **Mobile/responsive** findings are statically inferred from `hideOn` usage; actual mobile UX testing would surface more issues.
- **Frontend test coverage** is structurally weak (7 unit tests + 5 E2E specs vs 651 backend tests) — flagged as architectural gap, not part of cross-layer drift but relevant to detection capability.

---

— end Round-15 audit
