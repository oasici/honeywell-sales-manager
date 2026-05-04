# Cross-Layer Audit Report — Honeywell Sales Suite (Round 4, post-v1.8.5)

**Date:** 2026-05-04
**Branch:** `deploy/render-sandbox`
**HEAD:** `ea0ac0b` (post v1.8.5 — round-3's 30+ fixes shipped over v1.6.0..v1.8.5)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions · State/lifecycle · Schema-introspection sanity check (new requirement)

Synthesized from 6 parallel layer-focused scans (DB↔ORM, Backend↔API+tenant sweep, API↔Frontend types, Realtime+state+CACHE-1, Permissions+flags+PII+rate-limit, Naming+deferred-items). Headline claims re-verified against source before being included here.

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| **Total verified findings** | **84** |
| Critical | 17 |
| High | 36 |
| Medium | 23 |
| Low | 8 |

### Top headline issues — single hotfix PR before anything else

1. **R4-TEN-3** — `users.py` admin endpoints (toggle-active / change-role / reset-password) accept any `user_id` with **zero tenant scope**. A SALES_MANAGER in tenant A can reset the password of any manager in tenant B → instant tenant takeover. **Highest blast radius in the audit.**
2. **R4-CLOSE-1 / R4-TEN-5** — `Invoice` has no `tenant_id` anywhere (model + migration + 5 endpoints). Every authenticated user can list / read / mutate every other tenant's invoices. The migration's own docstring at `20260503_create_invoices.py:18` admits the gap.
3. **R4-PERM-1** — `FieldPermissionService.apply_to_response` is **dead code** (zero call sites across the entire backend). The whole field-level KVKK masking feature is admin theater — admins configure rules that are never enforced. Reps see un-masked PII regardless of policy.
4. **R4-TEN-2 / R4-TEN-4** — KVKK data export and customer-anonymize endpoints both accept cross-tenant `user_id` / `customer_id`. A breached manager account in tenant A can export tenant B's PII bundle or **irreversibly anonymize** tenant B's customers.
5. **R4-TEN-14** — `ReportEngine.execute_report` builds dynamic SELECTs on Quote/Opportunity/Customer/Email with **no tenant predicate**. A manager in A executes a B-owned template = arbitrary cross-tenant exfiltration as Excel/CSV/JSON.
6. **R4-PII-1** — Calendar OAuth tokens stored plaintext JSON in `settings` table. The `oauth_token_encrypted` model column exists but is unused. KVKK Article 12 violation on a backup leak.
7. **R4-DB-1** — Eight tables (`audit_logs`, `coaching_plans`, `competitor_mentions`, `forecast_snapshot_details`, `territories`, `territory_assignments`, `subscriptions`, `revenue_schedules`, `revenue_schedule_entries`) exist only via `metadata.create_all()` — no migration ever creates them. Same shape that produced DB-7 / DB-6 last sprint. Plus customers, quotes, and OpportunityFeaturesDaily have model-only column drift.
8. **R4-TS-1** — `PlaybookAnalyticsPage` will throw at render time. Backend returns `most_triggered: string | null`; TS declares it as an array; JSX calls `.length` and `.map(item => item.name)`. The page is unmountable as soon as one playbook execution exists.

### Most-affected surfaces

- **Multi-tenant isolation on broad surface area** (24 findings, 9 critical) — round-2/3 closed Quote/Customer/Lead/Opportunity bulk-action and merge paths; round-4 finds the same anti-pattern across Invoice, Contract, Subscription, RevenueSchedule, Signature, Webhook, WorkflowRule, ApprovalRule, Sequence/Segment, ReportTemplate+ReportEngine, Pricing/Bundles, Territory/Team, Forecast, Comments, Chat, Engagement, Compliance, Users admin, KVKK export, AI helpers, v5/v6/v9 intelligence, analytics drill-down, emails, calendar OAuth.
- **Schema drift via `create_all`** (16 findings) — the team is adding models faster than migrations. Eight tables completely missing migrations; multiple existing tables have model-only columns the migration never declared. Pattern recurring after round-3 closed two instances.
- **Mutation invalidation gaps in TanStack Query** (12 findings) — round-3 deferred this; round-4 enumerates 12 specific sites where a mutation succeeds and the related caches go stale (kanban after stage change, list after lead convert, contracts after invoice paid, etc).
- **DTO regressions / TS type drift** (17 findings) — the round-3 round-trip-tenant pattern was missed on `_opp_to_dict` and `_lead_to_dict`; SparePart has 4 distinct drift items; Quote `pdf_path` ghost field; Opportunity `source` returned but missing from TS; ApprovalRule `escalation_hours` orphaned.
- **Feature-flag gating** (1 mega-finding + 4 supporting) — `<FeatureFlagGate>` component **does not exist**. 30+ frontend routes are flag-less; 17 backend flags aren't even exposed to the frontend. Round-3's "5-minute mechanical fix" cannot proceed without first authoring the gate component.

---

## 2. Findings by Category

### 2.1 Multi-tenant security — CRITICAL (× 9), HIGH (× 14)

#### R4-TEN-3 — `users.py` admin actions cross-tenant — **CRITICAL**
- **File:** [backend/app/api/v1/users.py:64–159](../../backend/app/api/v1/users.py#L64) — `toggle_user_active`, `change_user_role`, `reset_user_password`. All three load `select(User).where(User.id == user_id)` (lines 71, 111, 150) with no tenant check. Verified: zero `tenant_id` / `assert_same_tenant` / `scoped_for_user` in the entire file.
- **Attack:** Manager in tenant A resets password of a manager in tenant B → instant tenant takeover. Worst possible blast radius in the codebase.
- **Fix:** `assert_same_tenant(user, current_user, exception_cls=NotFoundException)` after each load. The "last manager" guard at lines 80-89/120-128 should also be tenant-scoped.

#### R4-TEN-5 — `invoices.py` entirely unscoped — **CRITICAL**
- **File:** [backend/app/api/v1/invoices.py](../../backend/app/api/v1/invoices.py) — Invoice model has **no `tenant_id`** ([invoice.py:13-46](../../backend/app/models/invoice.py#L13)); list, get, update, status-transition, from-quote conversion, and `_generate_invoice_number` all touch Invoice rows with zero tenant filter. The `invoice.paid` event publishes `customer_id`/`quote_id` from a foreign tenant.
- **Attack:** Any user can `GET /invoices/` and see every other tenant's invoices, `PATCH /invoices/{id}/status` to mark a foreign invoice `paid` (triggering `invoice.paid`), or `PUT /invoices/{id}` to edit foreign drafts.
- **Fix:** **Two-step** — (1) add `Invoice.tenant_id` + migration backfilling from `customer.tenant_id`; (2) wrap every query with `scoped_for_user(stmt, current_user, column=Invoice.tenant_id)`. Note the `INV-2026-NNNN` numbering at line ~95 is a global counter — needs to become per-tenant too.

#### R4-TEN-6 — `contracts.py` entirely unscoped — **CRITICAL**
- **File:** [backend/app/api/v1/contracts.py:80–273](../../backend/app/api/v1/contracts.py#L80). Contract has no `tenant_id`. `list_contracts`, `get_contract` (uses `db.get`), `update_contract`, `amend_contract`, `activate_contract`, `expiring_contracts` — all unscoped.
- **Attack:** Any user can read and mutate every tenant's `terms_json`, set them `active`, sign them off via `signed_by = current_user.full_name`.
- **Fix:** Same as TEN-5 — add `Contract.tenant_id` + scope, OR join through Customer. Option 1 is cleaner.

#### R4-TEN-7 — `subscriptions.py` + `SubscriptionService` unscoped — **CRITICAL**
- **Files:** [subscriptions.py:50-133](../../backend/app/api/v1/subscriptions.py#L50), [subscription_service.py:24-90](../../backend/app/services/subscription_service.py#L24). Subscription has no `tenant_id`. List/detail/cancel/renew all by id; MRR dashboard at line 50 sums all tenants.
- **Attack:** `GET /subscriptions/mrr-dashboard` is a competitive-intelligence leak across tenants. Cancel/renew callable cross-tenant.
- **Fix:** Add `Subscription.tenant_id` + migration; refactor service to take `current_user`; scope all queries.

#### R4-TEN-8 — `revenue_recognition.py` unscoped + destructive ops — **CRITICAL**
- **File:** [revenue_recognition.py:95-324](../../backend/app/api/v1/revenue_recognition.py#L95). RevenueSchedule + RevenueScheduleEntry have no `tenant_id`. Dashboard at [:287-324](../../backend/app/api/v1/revenue_recognition.py#L287) sums all tenants.
- **Attack:** Mark a foreign tenant's entry `recognized` (line 243-284, irreversible) to corrupt their books.
- **Fix:** Add tenant_id, propagate into entries on insert, scope all queries.

#### R4-TEN-9 — `signatures.py` document handlers cross-tenant — **CRITICAL**
- **File:** [signatures.py:80-153](../../backend/app/api/v1/signatures.py#L80). `_load_document_summary` and `_apply_document_status_update` load Quote/Contract/Invoice by id with no tenant filter. The latter mutates `quote.status='accepted'`, `contract.status='active'`, `invoice.status='paid'`.
- **Attack:** Send-for-signature path lets anyone create a `SignatureRequest` for a foreign tenant's quote and the public sign callback flips its terminal status.
- **Fix:** `assert_same_tenant(doc, current_user, ...)` in both helpers.

#### R4-TEN-2 — `audit.py` KVKK data export ignores target user's tenant — **CRITICAL**
- **File:** [audit.py:167-225](../../backend/app/api/v1/audit.py#L167). `select(User).where(User.id == target_user_id)` (line 182) then bundles audit log + customers + opportunities + emails — no `target_user.tenant_id == current_user.tenant_id` check.
- **Attack:** Breached manager in tenant A iterates user IDs, pulls every PII bundle in tenant B.
- **Fix:** `assert_same_tenant(user, current_user, exception_cls=HTTPException(404))` after load. Also scope per-relationship queries.

#### R4-TEN-4 — `compliance.py` KVKK consent / export / delete cross-tenant — **CRITICAL**
- **File:** [compliance.py:80-337](../../backend/app/api/v1/compliance.py#L80). `record_consent`, `get_consent`, `export_customer_data`, `anonymize_customer_data`, `customer_audit_trail` — all load `select(Customer).where(Customer.id == customer_id)` with no tenant filter.
- **Attack:** Manager from A can (a) export tenant B customer's PII bundle, (b) **anonymize tenant B's customer** (irreversible — overwrites name/email/phone/address/tax_id with stubs).
- **Fix:** `assert_same_tenant(customer, current_user, ...)` after every Customer load.

#### R4-TEN-1 — Quote write paths bypass tenant scope (manager bypass) — **CRITICAL**
- **Files:** [quotes.py:240-264](../../backend/app/api/v1/quotes.py#L240) (update), [:496-549](../../backend/app/api/v1/quotes.py#L496) (convert-currency), [:436-489](../../backend/app/api/v1/quotes.py#L436) (PDF download), [:552-610](../../backend/app/api/v1/quotes.py#L552) (versions chain).
- **Pattern:** Loads quote, then ownership check `existing.created_by != current_user.id` short-circuits when role == SALES_MANAGER. Round-3 fixed only `approve` and `send`; the four sibling write/read paths above remain. The version walker at [:575-602](../../backend/app/api/v1/quotes.py#L575) loads parent/child by FK without a tenant guard either.
- **Fix:** `assert_same_tenant(existing, current_user, ...)` immediately after each `scalar_one_or_none()` and inside the version walker.

#### R4-TEN-14 — `ReportEngine.execute_report` injects no tenant predicate — **CRITICAL**
- **Files:** [reports_v2.py:436, 532](../../backend/app/api/v1/reports_v2.py#L436), [report_engine.py:157-185](../../backend/app/services/report_engine.py#L157).
- **Pattern:** ReportTemplate has no `tenant_id`. `_get_user_template` does owner-or-manager check (manager bypass). Engine then runs the user-supplied entity_type/columns/filters on `(Quote|Opportunity|Customer|Email)` with no tenant scope in the join logic.
- **Attack:** Cross-tenant arbitrary-shape exfiltration via the reporting layer. Worst-case data theft path in the audit aside from password reset.
- **Fix:** (1) add `ReportTemplate.tenant_id` + scope CRUD; (2) **most important**: in `ReportEngine.execute_inline`, inject `WHERE model.tenant_id = current_user.tenant_id` for every entity_type the engine knows about; refuse entities without `tenant_id`.

#### HIGH-severity tenant gaps (one-line summaries)

| ID | File:line | Issue |
|---|---|---|
| R4-TEN-10 | [webhooks.py:126-233](../../backend/app/api/v1/webhooks.py#L126) | Webhook get/update/delete cross-tenant; **`secret` field returned to any manager** → forge events for tenant B |
| R4-TEN-11 | [workflow_rules.py:100-142](../../backend/app/api/v1/workflow_rules.py#L100) | Update/delete rules cross-tenant; modify foreign automations |
| R4-TEN-12 | [approvals.py:90-150](../../backend/app/api/v1/approvals.py#L90) | ApprovalRule CRUD cross-tenant |
| R4-TEN-13 | [engagement.py:383-845](../../backend/app/api/v1/engagement.py#L383) | Sequence/SequenceEnrollment/Segment endpoints cross-tenant; pause/resume foreign nurture cadence |
| R4-TEN-15 | [pricing.py:103-167](../../backend/app/api/v1/pricing.py#L103), [bundles.py:80-140](../../backend/app/api/v1/bundles.py#L80) | CustomerPricing/ProductBundle exposed; negotiated prices leak |
| R4-TEN-16 | [territories.py:204-254](../../backend/app/api/v1/territories.py#L204), [teams.py:128-251](../../backend/app/api/v1/teams.py#L128) | Territory/Team metrics aggregate across tenants; SharingRule tampering |
| R4-TEN-17 | [forecast.py:42-100](../../backend/app/api/v1/forecast.py#L42), [:244-330](../../backend/app/api/v1/forecast.py#L244) | `/hybrid` and `/accuracy` see foreign pipeline |
| R4-TEN-18 | [comments.py:55-152](../../backend/app/api/v1/comments.py#L55) | Read/post comments on any entity; @-mention foreign tenant users |
| R4-TEN-19 | [chat.py:140-340](../../backend/app/api/v1/chat.py#L140) | ChatSession + AutoResponseRule cross-tenant; agent takeover of foreign customer chat |
| R4-TEN-20 | [v9_gap_closure.py:348-375](../../backend/app/api/v1/v9_gap_closure.py#L348) | Review-queue decide route bypasses tenant for managers |
| R4-TEN-21 | [v5_intelligence.py:57-71](../../backend/app/api/v1/v5_intelligence.py#L57), [v6_intelligence.py:60-72](../../backend/app/api/v1/v6_intelligence.py#L60) | `_load_opportunity` only checks owner_id for reps |
| R4-TEN-22 | [analytics.py:1205-1213](../../backend/app/api/v1/analytics.py#L1205) | Drill-down loads Customer/Opportunity unscoped |
| R4-TEN-23 | [emails.py:172, 362, 396, 408+](../../backend/app/api/v1/emails.py#L172) | EmailRequest endpoints unscoped + opportunity cross-load |
| R4-TEN-24 | [ai.py:487, 545, 666, 674, 1137, 1148](../../backend/app/api/v1/ai.py#L487) | AI helpers feed cross-tenant entities to generation |

#### Service-layer / DTO companions

- **R4-DTO-1** — `_opp_to_dict` does NOT include `tenant_id` (regression vs round-3 plan). `_quote_to_dict` (line 713) and `_customer_to_dict` (line 934) do. Fix: insert `"tenant_id": getattr(opp, "tenant_id", None)` in [opportunities.py:111-173](../../backend/app/api/v1/opportunities.py#L111).
- **R4-DTO-2** — `_lead_to_dict` does NOT include `tenant_id`. Same fix shape in [leads.py:565-587](../../backend/app/api/v1/leads.py#L565).
- **R4-DTO-3** — `_invoice_to_dict` returns money fields as `float` (precision loss); migrate to `Numeric(15, 2)` and string-encode.
- **R4-DTO-4** — `_serialize_contract` returns full `terms_json` (could be 200kB legal text) on every list-page hit. Strip on list, keep on detail.
- **R4-SVC-3** — `ReportEngine.execute_report/execute_inline` accepts naked id, builds dynamic SELECTs without `current_user`. Pass `current_user` and inject WHERE tenant predicate per entity. (Pairs with R4-TEN-14.)
- **R4-SVC-1** — `SubscriptionService` accepts naked IDs, does its own select with no tenant context.
- **R4-SVC-2** — `QuoteService._get_quote_or_raise` is a generic ID lookup with no tenant check; pushing the assertion into the helper would eliminate 5+ route-side bug classes.

### 2.2 Database ↔ Backend ORM — CRITICAL (× 2), HIGH (× 4)

#### R4-DB-1 — Eight tables exist only via `metadata.create_all()`, no migration — **CRITICAL**
- **Tables:** `audit_logs`, `coaching_plans`, `competitor_mentions`, `forecast_snapshot_details`, `territories`, `territory_assignments`, `subscriptions`, `revenue_schedules`, `revenue_schedule_entries`.
- **Models:** [audit_log.py:9-30](../../backend/app/models/audit_log.py#L9), [coaching_plan.py:13-34](../../backend/app/models/coaching_plan.py#L13), [competitor_mention.py:13-34](../../backend/app/models/competitor_mention.py#L13), [forecast_snapshot_detail.py:13-38](../../backend/app/models/forecast_snapshot_detail.py#L13), [territory.py:13-74](../../backend/app/models/territory.py#L13), [subscription.py:11-41](../../backend/app/models/subscription.py#L11), [revenue_recognition.py:13-58](../../backend/app/models/revenue_recognition.py#L13).
- **Worse:** [20260426_model_drift_align.py:139-171](../../backend/alembic/versions/20260426_model_drift_align.py#L139) adds FK constraints from `customers.territory_id`/`opportunities.territory_id` to `territories(id)` wrapped in `EXCEPTION WHEN duplicate_object` — but the underlying error on a fresh env is `undefined_table`, not `duplicate_object`, so the migration aborts.
- **And:** [20260428_v13_audit_tenant.py:38](../../backend/alembic/versions/20260428_v13_audit_tenant.py#L38) does `ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tenant_id` — fails hard if `audit_logs` doesn't exist.
- **Fix:** Author `20260504_create_missing_core_tables.py` mirroring the DB-7 pattern with `CREATE TABLE IF NOT EXISTS …` for all eight tables, plus indexes + `__table_args__` declarations, then re-order FKs.

#### R4-DB-2 — `customers.tenant_id`, KVKK fields, enrichment fields, `territory_id` have no migration — **CRITICAL**
- **Migration:** Partial — `20260426_model_drift_align.py:104-110` adds 8 columns; `20260427_v8_crm_tenant_id.py:31-34` adds `tenant_id`; the **base `customers` table itself is never created** by migration.
- **Model:** [customer.py:15-96](../../backend/app/models/customer.py#L15) — `name`, `company`, `email`, `phone`, `address`, `tax_id`, KVKK columns L41-L56 — all `create_all`-only.
- **Impact:** Identical to R4-DB-1; on a fresh env the table boots missing the KVKK consent columns and any insert with them throws `UndefinedColumn`.

#### R4-DB-3 — `quotes.version`, `pdf_path`, `close_reason`, `closed_at` missing from any migration — HIGH
- [quote.py:51-63](../../backend/app/models/quote.py#L51) — fresh env loses Win/Loss tracking and PDF path. Same hazard.

#### R4-DB-5 — `crm_sync_jobs` index column-direction drift — HIGH
- Migration: `started_at DESC` ([20260428_v9_crm_sync.py:83](../../backend/alembic/versions/20260428_v9_crm_sync.py#L83))
- Model: plain ASC ([v9_crm_sync.py:93](../../backend/app/models/v9_crm_sync.py#L93))
- Postgres treats them as different indexes; next autogenerate proposes drop+recreate, killing the recent-jobs scan plan.

#### R4-DB-6 — `customers.email` UNIQUE not enforced by any migration — HIGH
- Model declares `unique=True, nullable=False, index=True` ([customer.py:21](../../backend/app/models/customer.py#L21)); no migration creates the unique index. On a fresh env bootstrapped from SQL dump the constraint may have been stripped.

#### R4-DB-7 — `tenant_id` columns lack FK to `tenants(id)` everywhere — MEDIUM
- Every `tenant_id` across V7/V8/V13 is plain `Integer`. No referential integrity. Either commit to never-FK with an ADR or add deferred FKs.

#### R4-DB-8/9/10 — Nullable / default mismatches — MEDIUM
- `OpportunitySignal.is_resolved` (model nullable, migration NOT NULL), `Opportunity.probability` (model nullable comment is wrong), `meeting_auto_links.confidence` (no nullable=False or server_default in model). Future autogenerate will *weaken* prod constraints.

#### R4-DB-1 (events) — `DomainEvent.created_at` nullable — MEDIUM
- Model: [sequence_v2.py:75-77](../../backend/app/models/sequence_v2.py#L75) `nullable=True`, no `server_default`. Producer always sets it, so safe today; a hand-written backfill insert could land NULL and break index-driven `ORDER BY created_at DESC`.

### 2.3 Backend ↔ API contract / DTO drift

(See R4-DTO-1..4 above in the tenant section, plus:)

- **R4-VAL-1** — `QuoteResponse` Pydantic schema ([schemas/quote.py:69-95](../../backend/app/schemas/quote.py#L69)) lacks `tenant_id`, `opportunity_id`, `has_pdf`, `email_request_id`, `closed_at`, `close_reason`. Schema is unused as `response_model` so no runtime risk; fix or delete.
- **R4-DTO-5** — `_serialize` (subscription) lacks `tenant_id` (consequence of R4-TEN-7).
- **R4-DTO-6** — Architectural: most DTOs (Contract, Invoice, Subscription, Signature, Comment, Notification, Webhook, Territory, Team, Sequence, Segment, ReportTemplate, RevenueSchedule, ChatSession) cannot round-trip `tenant_id` because the underlying tables don't have it.

### 2.4 API ↔ Frontend type drift

#### R4-TS-1 — `PlaybookAnalyticsPage` will throw at render — **CRITICAL**
- **Backend:** [playbooks.py:244-246](../../backend/app/api/v1/playbooks.py#L244) returns `most_triggered: per_playbook[0]["playbook_name"] if per_playbook else None` (string-or-null). `per_playbook` rows have keys `playbook_name`/`total_executions`/`completed`/`cancelled`/`completion_rate`/`playbook_id`.
- **TS:** [types.ts:996-1004](../../frontend/src/lib/types.ts#L996) declares `per_playbook: { playbook_id; name; executions; completed }[]` and `most_triggered: { playbook_id; name; count }[]`.
- **UI:** [PlaybookAnalyticsPage.tsx:107-145](../../frontend/src/features/playbooks/PlaybookAnalyticsPage.tsx#L107) reads `item.name` / `.executions` / `.completed` and `most_triggered.length` + `most_triggered.map(item => item.name)`.
- **Impact:** Every column in per-playbook table renders `undefined`; `most_triggered.length` throws `Cannot read properties of null` on a string. Page is unmountable as soon as one playbook execution exists.
- **Fix:** Backend — emit `most_triggered` as `[{playbook_id, name, count}, …]` (top-5 of `per_playbook`). Frontend — also rename `per_playbook` keys (`name`/`executions`/`completed`) to match.

#### Other TS drifts

| ID | Severity | Field | Issue |
|---|---|---|---|
| R4-TS-2 | high | `Quote.pdf_path` | Backend dropped it (TS-2 cleanup); TS still marks required → `undefined` at runtime |
| R4-TS-3 | high | `ApprovalRule.escalation_hours/escalation_action` | Backend returns; TS missing → orphaned data + R4-RENDER-2 |
| R4-TS-4 | high | `Opportunity.source` | Round-3 DB-6 fix returns it; TS missing → consumers must cast → R4-RENDER-3 |
| R4-TS-5 | medium | `Sequence.auto_enroll_rules` | List endpoint omits, detail returns; TS marks required-not-undefined |
| R4-TS-6 | medium | `SequenceEnrollment.next_action_at/sequence_name` | Backend returns; TS missing |
| R4-TS-7/8 | low | `Pipeline.updated_at`, `Territory.updated_at` | Backend returns; TS missing |
| R4-TS-10 | medium | local `Lead` interface in `LeadListPage` | Drifts from backend; promote to central `types.ts` |
| R4-TS-11 | low | `Customer.kvkk_*` | Intentionally omitted but undocumented; add comment |

#### API client envelope drift (consequence of round-3 not finishing the standardisation)

- **R4-API-1** — `getNotifications<T = unknown>` still uses generic in [api.ts:805-816](../../frontend/src/lib/api.ts#L805); drop and return `Promise<Notification[]>`.
- **R4-API-2** — `/notifications/` lacks pagination envelope (`{notifications: [...]}` only).
- **R4-API-3** — Meeting endpoints ([meetings.py:73-252+](../../backend/app/api/v1/meetings.py#L73)) wrap responses in `{data: ...}` — non-canonical, double-unwrap required.
- **R4-API-4** — `/pipelines/`, `/deal-rooms/`, `/territories/` use legacy root keys (`{pipelines: ...}` etc); mirror the sequences-style transitional envelope.

### 2.5 Data fetched but not rendered (NEW only)

- **R4-RENDER-1** — `_lead_to_dict` returns `notes`, `owner_name`, `updated_at`; LeadListPage drops them all.
- **R4-RENDER-2** — Approval rules' `escalation_hours` fetched but no UI surfaces it (pairs with R4-TS-3).
- **R4-RENDER-3** — Opportunity `source` round-trips but board / detail show nothing (pairs with R4-TS-4).

### 2.6 Realtime / Event bus / State / CACHE-1 (round-3 deferred → executed)

#### R4-CACHE-101..112 — Mutation invalidation gaps — **HIGH (× 7), MEDIUM (× 5)**

| ID | Site (file:line) | Misses |
|---|---|---|
| R4-CACHE-101 | [OpportunityDetailPage.tsx:418-427](../../frontend/src/features/board/OpportunityDetailPage.tsx#L418) | `['opportunity', oppId]`, kanban list, AI cards |
| R4-CACHE-102 | [QuoteEditorPage.tsx:126-142](../../frontend/src/features/quotes/QuoteEditorPage.tsx#L126) | `['quotes']`, `['notifications']`, opp timeline |
| R4-CACHE-103 | [LeadDetailPage.tsx:157-172](../../frontend/src/features/leads/LeadDetailPage.tsx#L157) | `['leads']`, `['customers']`, `['opportunities']`, `['campaign-members']` |
| R4-CACHE-105 | [MergeRecordsPage.tsx:174-188](../../frontend/src/features/admin/MergeRecordsPage.tsx#L174) | Invalidates **nothing** — full sweep needed |
| R4-CACHE-106 | [InvoiceDetailPage.tsx:69-77](../../frontend/src/features/invoices/InvoiceDetailPage.tsx#L69) | Contract caches, rev-rec, cockpit |
| R4-CACHE-107 | [CustomerDetailPage.tsx:253-261](../../frontend/src/features/customers/CustomerDetailPage.tsx#L253) | `['customers']`, search, account-360, intelligence |
| R4-CACHE-104, 108-112 | various | Detail-page mutations miss adjacent caches |

**Pattern recommendation:** Author `frontend/src/lib/cacheInvalidation.ts` exposing `onOpportunityChanged(qc, oppId)` / `onCustomerChanged(qc, customerId)` / `onLeadConverted(qc, leadId)` etc. Point fixes will rot.

#### R4-EG-1 — Dead-letter event store still missing — HIGH (re-confirmed)

- [event_bus.py:36-82](../../backend/app/core/event_bus.py#L36) on retry exhaustion calls `sentry_sdk.capture_exception` then **drops the payload**. No DB persistence, no replay path.
- `domain_events` table only stores **successful** publishes ([domain_events.py:124-141](../../backend/app/services/domain_events.py#L124)); failed deliveries vanish.
- **Design (proposal):** model `DeadLetterEvent(id, event_type, handler_name, payload_json, error_message, error_traceback, attempt_count, created_at, replayed_at, replayed_by)`; `GET /api/v1/admin/dead-letter-events` (paginated, manager-only); `POST /api/v1/admin/dead-letter-events/{id}/replay`. Wire into existing `EventAuditLogPage.tsx:76` polling.

#### R4-EVT-201..205 — Event bus drift

| ID | Issue | Severity |
|---|---|---|
| R4-EVT-201 | `customer.created` subscribed at [main.py:203](../../backend/app/main.py#L203) but **never emitted** anywhere → webhook subscribers configured for it never fire | Medium |
| R4-EVT-203 | `_on_invoice_paid` is a `pass` stub at [main.py:234-238](../../backend/app/main.py#L234); contract.actual_revenue never auto-incremented | Low |
| R4-EVT-204 | No commit-discipline test for bus handlers | Medium |
| R4-EVT-205 | `revenue_signal.created` orphaned when `FEATURE_REVENUE_COCKPIT` off | Low |

#### R4-RT-300 — No SSE/WebSocket; everything is polled — MEDIUM (design)
- Zero `WebSocket`/`EventSource` in either layer. Chat is built on polling (3-5s lag). Notification badge can take up to 60s. Recommend single SSE endpoint + Redis pub/sub for fan-out.

#### R4-STATE-401 — `authStore.user` not refreshed when admin changes own role — LOW
- After `changeRoleMutation` on self, role stays stale until logout. Fix: `if (id === currentUser.id) useAuthStore.getState().bootstrap()`.

### 2.7 Permissions / Feature flags / PII / Rate limiting

#### R4-PERM-1 — `FieldPermissionService.apply_to_response` is dead code — **CRITICAL**
- **Verified:** [field_permission_service.py:70](../../backend/app/services/field_permission_service.py#L70) defines the masking logic. Grep across `backend/app/` shows ZERO call sites outside `field_permissions.py` (admin CRUD only).
- **Attack:** A SALES_REP queries `GET /customers/{id}` — backend returns full email/phone/tax_id even when admin configured `{role: 'sales_rep', entity: 'customer', field: 'email', access: 'masked'}`. Whole feature is admin theater.
- **Fix:** In every `_*_to_dict` (customers, leads, opportunities, quotes, emails), wrap response: `await field_perm_service.apply_to_response(data, current_user.role, 'customer')`. Test that masked `email` returns `o***@example.com`.
- **Frontend follow-up (R4-PERM-2):** Return `{value, masked: true}` so the UI can show a "request unmask" affordance.
- **R4-PERM-3:** `VALID_ENTITY_TYPES` ([field_permission_service.py:14](../../backend/app/services/field_permission_service.py#L14)) missing `contract`, `invoice`, `subscription`, `campaign`.

#### R4-PII-1 — Calendar OAuth tokens stored plaintext — **CRITICAL**
- **Verified:** [calendar_service.py:212](../../backend/app/services/calendar_service.py#L212) `serialized = json.dumps(tokens_with_timestamp)` then writes to `Setting.value`. The `v9_calendar.oauth_token_encrypted` column ([v9_calendar.py:35-36](../../backend/app/models/v9_calendar.py#L35)) is unused.
- **Attack:** Read-only DB compromise (backup leak, replica access) exposes access_token + refresh_token; indefinite calendar read/write per tenant. KVKK Article 12 violation.
- **Fix:** Route through `_get_fernet()` from [settings.py:32-49](../../backend/app/api/v1/settings.py#L32) (already used for SMTP password) when writing/reading `calendar_oauth_tokens`.

#### R4-PII-2 — E-sign provider config (`api_key`, `account_id`) plaintext — HIGH
- [integrations.py:447-452](../../backend/app/api/v1/integrations.py#L447) `json.dumps(body.config)` then writes Setting. Same shape as R4-PII-1; encrypt with Fernet.

#### R4-PII-3 — `ENCRYPTION_KEY` auto-generated in non-production — MEDIUM
- [settings.py:32-48](../../backend/app/api/v1/settings.py#L32) generates key into `os.environ` if missing. After dev restart all previously-encrypted SMTP passwords become undecryptable.

#### R4-PII-4 — No per-row encryption on `Customer/Contact/Lead` PII columns — MEDIUM
- Only `v9_calendar`/`v9_crm_sync` reserve `oauth_token_encrypted` (and even those are unused). The "ENCRYPTION_KEY decrypts per-row PII" claim in render.yaml is **not implemented**. Introduce `EncryptedString` `TypeDecorator` and apply to email/phone/tax_id/address with backfill migration.

#### R4-AUTH-1 — `/integrations/esign/webhook` gated by `require_role(SALES_MANAGER)` — HIGH
- [integrations.py:531-547](../../backend/app/api/v1/integrations.py#L531). External e-sign provider has no JWT → webhook silently never fires. Functional bug masquerading as auth.
- **Fix:** Drop `require_role`, add HMAC-SHA256 signature verification via `X-Esign-Signature`.

#### R4-AUTH-2 — `/integrations/calendar/callback` accepts unauthenticated `code` + `state` — HIGH
- [integrations.py:85-151](../../backend/app/api/v1/integrations.py#L85). Phished/replayed `code` lets attacker overwrite the **global** Setting tokens (no tenant scoping in `_save_tokens`, [calendar_service.py:202-219](../../backend/app/services/calendar_service.py#L202)) for ALL tenants.
- **Fix:** Validate `state` as session-tied CSRF token; scope token storage by `current_user.tenant_id`.

#### R4-FLAG-1 — 17 backend-gated features unreachable from frontend flag map — HIGH
- [config.py:32-59](../../backend/app/api/v1/config.py#L32) `_PUBLIC_FEATURE_FLAGS` is missing `FEATURE_REVENUE_COCKPIT`, `FEATURE_LEAD_LIFECYCLE`, `FEATURE_APPROVAL_ROUTING`, `FEATURE_DASHBOARD_BUILDER`, `FEATURE_REPORT_BUILDER`, `FEATURE_CUSTOM_FIELDS`, `FEATURE_FIELD_PERMISSIONS`, `FEATURE_PRODUCT_RULES`, `FEATURE_WORKFLOW_RULES`, `FEATURE_TERRITORIES`, `FEATURE_LIVE_CHAT`, `FEATURE_MULTI_PIPELINE`, `FEATURE_INVOICING`, `FEATURE_REV_REC`, `FEATURE_CAMPAIGNS`, `FEATURE_BREACH_WORKFLOW` (or new `FEATURE_COMPLIANCE`), and `FEATURE_COACHING/PLAYBOOKS` (currently overloaded onto `FEATURE_REVENUE_COCKPIT`).
- **Verified:** `<FeatureFlagGate>` component **does not exist**. [FeatureFlagContext.tsx:1-90](../../frontend/src/contexts/FeatureFlagContext.tsx#L1) only exports `useFeatureFlag` hook. Round-3's "5-minute mechanical fix" cannot proceed without first authoring the gate component.
- **Fix:** (1) Add 17 names to `_PUBLIC_FEATURE_FLAGS`; (2) Author `<FeatureFlagGate flag="FEATURE_X" fallback={<Forbidden/>}>`; (3) Wrap each route in App.tsx (table of 30+ routes in scanner output).

#### R4-FLAG-3 — `/compliance/*` has no backend flag check at all — HIGH
- [compliance.py:30-589](../../backend/app/api/v1/compliance.py#L30) — no `_require_feature` import. Tenant on a plan that doesn't include KVKK module can still call `/compliance/data-export/{customer_id}`.

#### R4-RL-2 — Bulk-action endpoints have no rate limit — HIGH
- [customers.py:708](../../backend/app/api/v1/customers.py#L708), [leads.py:384](../../backend/app/api/v1/leads.py#L384), [opportunities.py:698](../../backend/app/api/v1/opportunities.py#L698). User POSTs `{action: "delete", ids: [1..10000]}` repeatedly → DoS + audit-log flooding (after AUD-2 fix).
- **Fix:** Add `make_user_rate_limit("RATE_LIMIT_BULK", "5/minute", "Toplu islem limiti asildi")`.

#### R4-RL-3 — RAG search endpoints have no rate limit — HIGH
- [rag.py:72-147](../../backend/app/api/v1/rag.py#L72). Single user can burn through Anthropic/OpenAI budget on `/rag/answer`. Attach existing `enforce_ai_rate_limit` from [rate_limit.py:158-164](../../backend/app/core/rate_limit.py#L158).

#### R4-RL-4 / R4-RL-5 — KVKK + audit data-export endpoints have no rate limit — MEDIUM
- [compliance.py:161-265](../../backend/app/api/v1/compliance.py#L161), [audit.py:100,167](../../backend/app/api/v1/audit.py#L100). Iterate `/compliance/data-export/{1..N}` to exfiltrate entire KVKK PII corpus in minutes.

#### R4-RL-6 — `enforce_login_rate_limit` is IP-only — MEDIUM
- [rate_limit.py:82-93](../../backend/app/core/rate_limit.py#L82) — botnet with N IPs gets N × 5/minute attempts. Layer per-username limit on top.

#### Verified clean (positive findings)
- Sentry `before_send` PII scrubber is active and correct (TCKN/VKN/IBAN/CC) — [error_tracking.py:7-60](../../backend/app/core/error_tracking.py#L7).
- Outbound webhook HMAC signing is correct (legacy + v2 schemes) — [webhook_service.py:118-129](../../backend/app/services/webhook_service.py#L118).
- Login + refresh + change-password rate-limited.
- Snake_case end-to-end, no axios case-conversion interceptor.
- All IDs are int/number, no UUIDs in business tables.
- Date columns serialize via `str()` correctly (`YYYY-MM-DD`).

### 2.8 Naming / format / enum / shape / ID drift

| ID | Severity | Issue |
|---|---|---|
| R4-CLOSE-2a/b | medium | `SparePart` TS missing `keywords_json`/`aliases_json` ([types.ts:211-228](../../frontend/src/lib/types.ts#L211) vs [parts.py:307-308](../../backend/app/api/v1/parts.py#L307)) |
| R4-CLOSE-2c | medium | `min_margin_pct` on model never serialized |
| R4-CLOSE-2d | high | TS `SparePart.has_price` is a phantom field — no source |
| R4-CLOSE-3 | medium | Segments endpoint `{segments: [...]}` non-canonical envelope |
| R4-NAME-1 | medium | SparePart 6 string fields typed non-null but DB allows NULL |
| R4-FMT-1 | high | `EmailRequest.price_sensitivity` is `bool \| None` in DB but `string \| null` in TS — outright type lie |
| R4-SHAPE-1 | medium | `is_paused` tristate rendered as binary → `null` rendered as "active" |
| R4-FMT-3 | low | All money columns are `Float`, no `Numeric/Decimal` anywhere — note for scale |
| R4-ENUM-1/2 | low | `OpportunityStage`, `InvoiceStatus`, `EmailStatus`, `ReviewStatus`, `UserRole`, `TaskStatus/Source/Priority` not mirrored as TS unions |
| R4-SHAPE-2 | low | `GET /parts/categories` returns raw array (acceptable for enum source) |
| R4-SHAPE-3 | medium | `/engagement/sequences/` still ships raw `{sequences: [...]}` (round-3 A-11 deferred) |
| R4-NAME-3 | low | `Customer.tenant_id?` should not be optional in TS |

---

## 3. Schema-Introspection Sanity Check (new requirement — design spec)

**Location:** `backend/app/core/schema_check.py` (new) + `backend/scripts/check_schema_drift.py` (CLI for CI).

**Boot-time mode:**
1. Iterate `Base.registry.mappers`, get `mapper.local_table.{name, schema}`.
2. Skip tables flagged with `__table_args__ = {"info": {"skip_drift_check": True}}` (escape hatch).
3. Use `inspect(engine).get_columns(table, schema)` + `.get_indexes(...)`, `.get_unique_constraints(...)`, `.get_foreign_keys(...)`.
4. Per column compare `name`, `type` (use alembic's `_compare_type` so `String(20)` ≡ `VARCHAR(20)` and `TIMESTAMPTZ` ≡ `DateTime(timezone=True)`), `nullable`, `default`/`server_default`.
5. Aggregate into `SchemaDriftReport` dataclass: `missing_in_db`, `missing_in_model`, `type_mismatch`, `nullability_mismatch`, `index_mismatch`, `fk_mismatch`.

**`SCHEMA_DRIFT_MODE` env var:**
- `off` (default in prod) — skip.
- `warn` (default staging) — log structured JSON + Sentry breadcrumb (not event), grouped by table.
- `fail` (default dev + CI) — raise `SchemaDriftError`, refuse to start.

**Special cases:**
- Partitioned tables — query `pg_partitioned_table`; check parent only.
- Views — query `information_schema.views`; skip column comparisons.
- Schema-qualified tables — pass `schema=mapper.local_table.schema`.

**CI snippet (`.github/workflows/schema-check.yml`):**
```yaml
- name: Bootstrap test DB from migrations
  run: |
    psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    cd backend && alembic upgrade head
- name: Schema drift check
  env:
    SCHEMA_DRIFT_MODE: fail
  run: cd backend && python scripts/check_schema_drift.py
```
The CI step is the load-bearing one — it forces every PR adding a new column to also add a migration.

**Estimated effort:** ~250 LOC core + ~50 LOC CLI + 30 LOC CI.

---

## 4. Cross-Layer Schema Compatibility Matrix (key entities)

| Entity | DB column | Model field | API field | TS field | UI rendered? | Status |
|---|---|---|---|---|---|---|
| **Invoice** | (no `tenant_id`) | (no field) | (no field) | (no field) | n/a | **R4-CLOSE-1** missing everywhere |
| **Contract** | (no `tenant_id`) | (no field) | (no field) | (no field) | n/a | **R4-TEN-6** missing everywhere |
| **Subscription** | (no `tenant_id`) | (no field) | (no field) | (no field) | n/a | **R4-TEN-7** missing everywhere |
| **Opportunity** | `tenant_id` ✓ | ✓ | **missing in `_opp_to_dict`** | `tenant_id?` ✓ | n/a | **R4-DTO-1** |
| **Opportunity** | `source` ✓ (post DB-6) | ✓ | ✓ | **missing** | **never rendered** | **R4-TS-4 / R4-RENDER-3** |
| **Lead** | `tenant_id` ✓ | ✓ | **missing in `_lead_to_dict`** | (local interface) | n/a | **R4-DTO-2 / R4-TS-10** |
| **Lead** | `notes`, `owner_name`, `updated_at` ✓ | ✓ | ✓ | **missing on local interface** | **never rendered** | **R4-RENDER-1** |
| **Quote** | `pdf_path` (model only) | ✓ | dropped | required `string \| null` | n/a | **R4-DB-3 / R4-TS-2** |
| **ApprovalRule** | `escalation_hours/action` ✓ | ✓ | ✓ | **missing** | **never rendered** | **R4-TS-3 / R4-RENDER-2** |
| **SparePart** | `keywords_json/aliases_json` ✓ | ✓ | ✓ | **missing** | n/a | **R4-CLOSE-2a/b** |
| **SparePart** | (no field) | (no field) | (no field) | `has_price: boolean` | (always falsy) | **R4-CLOSE-2d** phantom |
| **EmailRequest** | `price_sensitivity` (`bool`) | ✓ | ✓ (`bool`) | `string \| null` ❌ | wrong | **R4-FMT-1** |
| **PlaybookAnalytics** | n/a (computed) | n/a | `most_triggered: str \| null` | `{playbook_id;name;count}[]` | crashes | **R4-TS-1** |

---

## 5. Fix Plan

### Hotfix PR (single PR — same shape as round-3 TEN-* hotfix)
1. **R4-TEN-3** — `users.py` admin endpoints (highest blast radius — password reset across tenants).
2. **R4-TEN-2** — KVKK data export tenant guard (compliance violation).
3. **R4-TEN-4** — KVKK customer-anonymize tenant guard (destructive + compliance).
4. **R4-TEN-1** — Quote update/PDF/convert/versions tenant guards (4 routes, same shape as round-3 TEN-6).

### Hotfix PR — security critical paired
5. **R4-PERM-1** — Wire `apply_to_response` into list/detail serializers (Customer, Lead, Opportunity, Quote, Email).
6. **R4-PII-1, R4-PII-2** — Encrypt OAuth tokens & e-sign API keys via Fernet.
7. **R4-AUTH-1, R4-AUTH-2, R4-WEBH-1** — Fix e-sign + calendar webhook auth model.

### Schema-required PR (one migration + scope sweep)
8. **R4-TEN-5/6/7/8** + **R4-CLOSE-1** — Add `tenant_id` to Invoice, Contract, Subscription, RevenueSchedule (+entries) in a single migration; backfill from parent rows in same window; scope all routes.
9. **R4-TEN-14** — Inject WHERE tenant predicate into ReportEngine for every entity_type once tenant_id is present.

### Per-feature scoping PRs (cluster as you can)
10. R4-TEN-9 (signatures), R4-TEN-10/11/12 (webhook/workflow/approval rules), R4-TEN-13 (engagement), R4-TEN-15 (pricing/bundles), R4-TEN-16 (territories/teams), R4-TEN-17/18/19 (forecast/comments/chat), R4-TEN-20/21/22/23/24 (v9/v5/v6/analytics/emails/ai).

### Schema drift PR
11. **R4-DB-1, R4-DB-2, R4-DB-3** — Author `20260504_create_missing_core_tables.py` mirroring DB-7 pattern with `CREATE TABLE IF NOT EXISTS` for the 8 missing tables + add columns missing on `customers`/`quotes`. Re-order FK creation in `20260426_model_drift_align.py`.

### Schema-introspection check PR
12. **Section 3** — Implement `schema_check.py` + CLI + CI step. Forces every future PR adding a column to also add a migration.

### Frontend correctness PR (TS-only)
13. **R4-TS-1** — Fix PlaybookAnalytics shape (will crash users today).
14. **R4-TS-2/3/4/5/6/7/8/10**, **R4-CLOSE-2a/b/d**, **R4-NAME-1**, **R4-FMT-1**, **R4-NAME-3** — Single TS-only PR aligning all type drift.

### Cache invalidation PR
15. Author `frontend/src/lib/cacheInvalidation.ts` helper. Apply to **R4-CACHE-101..112** (12 sites). Ship one-shot.

### Feature flag rollout PR
16. **R4-FLAG-1** — Add 17 missing flags to `_PUBLIC_FEATURE_FLAGS`; author `<FeatureFlagGate>`; wrap 30+ routes in App.tsx; gate `/compliance/*` (R4-FLAG-3) and `/subscriptions`/`/contracts` (R4-FLAG-4) on backend.

### Rate limiting PR
17. **R4-RL-2/3/4/5/6** — Bulk, RAG, KVKK export, audit export, login (per-username layer).

### Dead-letter + envelope cleanup PR
18. **R4-EG-1** — Dead-letter table + replay endpoint + admin UI hook.
19. **R4-API-1/2/3/4**, **R4-CLOSE-3**, **R4-SHAPE-3** — Envelope normalisation across notifications, meetings, pipelines, deal-rooms, territories, segments, sequences.

### Defer (medium / low / hardening)
- R4-PII-3, R4-PII-4 (per-row PII encryption refactor — own sprint).
- R4-DB-7 (tenant_id FK ADR or addition).
- R4-DB-8/9/10 (nullable/default cleanup sweep).
- R4-DTO-3 (Invoice money → Decimal) once Invoice has tenant_id.
- R4-DTO-4 (Contract `terms_json` strip on list).
- R4-EVT-201 (emit `customer.created`).
- R4-WEBH-3 (webhook secret rotation endpoint).
- R4-RT-300 (SSE/Redis pub/sub for realtime).
- R4-PERM-2/3 (frontend mask-aware UI; widen `VALID_ENTITY_TYPES`).
- R4-STATE-401 (refresh authStore.user after self-role change).

---

## 6. Tests to Add (priority — pair with the fix PRs above)

**Hotfix PR:**
- `test_toggle_active_rejects_other_tenant_user`
- `test_change_role_rejects_other_tenant_user`
- `test_reset_password_rejects_other_tenant_user`
- `test_kvkk_data_export_rejects_other_tenant_user_id`
- `test_kvkk_anonymize_rejects_other_tenant_customer`
- `test_update_quote_rejects_other_tenant`
- `test_download_pdf_rejects_other_tenant`
- `test_field_perm_apply_to_response_masks_email_for_sales_rep`

**Schema-required PR:**
- `test_invoice_list_filters_by_tenant`
- `test_invoice_status_rejects_other_tenant`
- `test_invoice_number_per_tenant_unique`
- `test_contract_activate_rejects_other_tenant`
- `test_subscription_mrr_dashboard_filters_by_tenant`
- `test_revenue_dashboard_filters_by_tenant`
- `test_report_engine_filters_by_tenant_for_each_entity_type`

**Schema check:**
- `test_schema_drift_check_passes_against_clean_migration_chain`
- `test_schema_drift_check_fails_when_model_has_column_not_in_db`

**Cache invalidation:**
- `test_quote_approve_invalidates_quotes_list_and_notifications`
- `test_lead_convert_invalidates_leads_customers_opportunities`
- `test_opportunity_stage_change_invalidates_kanban`

**Frontend correctness:**
- `PlaybookAnalyticsPage.test.tsx — renders without throwing when most_triggered is null/string`

---

## 7. Items needing manual verification

- **`record_duplicate_service.merge_records` body** — round-3 TEN-8 said route now passes `current_user`; not re-confirmed that the service actually calls `assert_same_tenant` on both rows.
- **Objection / RepDnaProfile** tenant_id columns referenced by v5_intelligence — assumed missing (absent from grep), but could store tenant via JSON or relationship.
- **`feature_store.py`, `target_alignment.py`, `ops.py`** — no obvious id-by-int-without-scope hits; not exhaustively read.
- **`/admin/system-health`, `/admin/event-audit`** — sidebar role-gates the link, but server-side `require_role` not confirmed in this round.
- **`EmailRequest.tenant_id`** — referenced as missing in R4-TEN-23 but not directly verified.
- **R4-CACHE-3** uses `['kanban']` as a guess for the board view query key — verify before patching.

---

## 8. Round-3 follow-ups confirmed in place (positive)

- TEN-1..8 (bulk-action / merge / approve / send tenant guards) ✓
- AUD-2 (log_activity inside bulk delete loop) ✓
- EVT-2/3/4/5 (score_changed events, sentry capture, required-field guards, webhook subscriber) ✓
- FLAG-2 (bogus public flags removed) ✓
- `_assert_entity_in_tenant` dispatcher in approvals.py ✓
- Quote `_quote_to_dict` and `_customer_to_dict` round-trip `tenant_id` ✓
- DB-5 (CustomFieldValue.value_date type drift) ✓
- DB-6 (Opportunity.source mapping) ✓
- DB-7 (invoices CREATE TABLE migration) ✓ — but **R4-CLOSE-1** finds the table now needs `tenant_id` added.

---

## 9. Round-3 claim corrected

Round-3 stated "Invoice has 16+ columns including `tenant_id`" — this was incorrect. The model has 16 columns, **none of which is `tenant_id`**. R4-CLOSE-1 / R4-TEN-5 are the corrective findings.

---

**Audit synthesised by 6 parallel scanners + verification spot-checks. All headline findings have file:line citations and were re-read against source before inclusion.**
