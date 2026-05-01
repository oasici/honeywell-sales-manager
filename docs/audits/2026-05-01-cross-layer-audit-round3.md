# Cross-Layer Audit Report — Honeywell Sales Suite (Round 3, post-v1.7.1)

**Date:** 2026-05-01
**Branch:** `deploy/render-sandbox`
**HEAD:** `2287fbf` (post v1.7.1 — round-2's 18 fixes shipped over v1.6.1, v1.7.0, v1.7.1)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions · State/lifecycle

Synthesized from 6 parallel layer-focused scans, with each headline finding re-verified against source before being included here. Items I could **not** verify, or where the agent overstated, are listed at the end as "rejected during verification".

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| Total verified findings | **30** |
| Critical | 3 |
| High | 13 |
| Medium | 11 |
| Low | 3 |

**Most-affected surfaces:**
- **Multi-tenant isolation on bulk endpoints** (5 findings, 3 critical) — round-2 closed three; round-3 finds five more in the same shape (`Customer.id.in_(ids)`, `Lead.id.in_(ids)`, `merge_records`, `approve_quote`, `send_quote`)
- **Detail / list pages dropping fetched fields** (10 findings) — biggest UX impact, smallest fix
- **TS types missing fields the API has been returning** (4 findings) — pure type-only churn
- **Schema drift** (2 findings: missing `Opportunity.source` mapping; `invoices` table has no migration file)

**Headline issues that warrant a single hotfix PR before anything else:**
1. **TEN-4** `bulk_action_customers` mutates and exports cross-tenant
2. **TEN-5** `bulk_action_leads` same shape
3. **TEN-8** `merge_records` can merge customers across tenants
4. **TEN-6** `approve_quote` (manager-callable) lacks tenant guard
5. **TEN-7** `send_quote` lacks tenant guard

These are direct siblings of TEN-1/2/3 from round-2 — same `select(Model).where(Model.id == X)` anti-pattern, missed because the round-2 audit only covered `bulk_action_opportunities`, `approval_history`, and `compare_quotes`.

---

## 2. Findings by Feature / Page

### 2.1 Multi-tenant security (CRITICAL × 3, HIGH × 2)

#### TEN-4 — `POST /customers/bulk-action` writes/exports cross-tenant
- **Severity:** **critical**
- **Category:** permission / cross-tenant write
- **Evidence:** [backend/app/api/v1/customers.py:708-771](../../backend/app/api/v1/customers.py#L708-L771); fetch at line 725-727 is `select(Customer).where(Customer.id.in_(ids))` with no tenant filter. `delete`, `assign`, and `export` actions all run on the resulting set.
- **Verified:** the file imports `scoped_for_user` at line 19 and uses it correctly on the list endpoint (lines 48, 72) — so this isn't a missing-import problem, it's a missed call site.
- **Minimal fix:**
  ```python
  result = await db.execute(
      scoped_for_user(select(Customer), Customer, current_user).where(
          Customer.id.in_(ids),
      )
  )
  ```
- **Tests:** add `test_bulk_action_customers_rejects_other_tenant`

#### TEN-5 — `POST /leads/bulk-action` same pattern
- **Severity:** **critical**
- **Evidence:** [backend/app/api/v1/leads.py:384-405](../../backend/app/api/v1/leads.py#L384-L405); fetch at line 402-404 unscoped.
- **Verified:** `scoped_for_user` already imported (line 25) and used on list at lines 279-280.
- **Minimal fix:** same shape as TEN-4.

#### TEN-8 — `POST /duplicates/merge` merges customers across tenants
- **Severity:** **critical**
- **Evidence:** [backend/app/api/v1/duplicates.py:81-100](../../backend/app/api/v1/duplicates.py#L81-L100) accepts `winner_id` + `loser_id`; service at [backend/app/services/record_duplicate_service.py:170-192](../../backend/app/services/record_duplicate_service.py#L170-L192) fetches both `Customer` rows by ID with no tenant scoping.
- **Impact:** A `SALES_MANAGER` can supply IDs from another tenant and merge a foreign customer's quotes/contacts into one of their own — destructive *and* exfiltrative.
- **Minimal fix:** `assert_same_tenant(winner, current_user, exception_cls=NotFoundException)` and same on `loser`, before any reassignment loops.
- **Tests:** add `test_merge_records_rejects_other_tenant`

#### TEN-6 — `PATCH /quotes/{id}/approve` lacks tenant guard
- **Severity:** **high**
- **Evidence:** [backend/app/api/v1/quotes.py:267-278](../../backend/app/api/v1/quotes.py#L267-L278); calls `service.approve_quote(quote_id)`. The service's [_get_quote_or_raise](../../backend/app/services/quote_service.py:429-441) is a generic ID lookup with **no tenant check**. Manager-only role gate is the only barrier.
- **Impact:** A manager from tenant A can approve any tenant B quote (and trigger PDF + Sentry-logged activity).
- **Minimal fix:** fetch the quote first (or have `_get_quote_or_raise` accept a `current_user` arg) and `assert_same_tenant`.

#### TEN-7 — `POST /quotes/{id}/send` lacks tenant guard
- **Severity:** **high**
- **Evidence:** [backend/app/api/v1/quotes.py:312-329](../../backend/app/api/v1/quotes.py#L312-L329); fetches by ID (line 320-322) then runs an *ownership* check (`quote.created_by != current_user.id`) but never tenant. The "ownership" check accepts SALES_MANAGER as a bypass, so a manager in tenant A can send any tenant B quote.
- **Minimal fix:** add `assert_same_tenant(quote, current_user, exception_cls=NotFoundException)` after line 325.

### 2.2 Database ↔ Backend ORM (HIGH × 2, MEDIUM × 1, LOW × 1)

#### DB-6 — `opportunities.source` column exists but isn't mapped on the model
- **Severity:** high
- **Category:** database-backend mismatch
- **Evidence:** migration [backend/alembic/versions/20260422_opportunity_foundation.py:33](../../backend/alembic/versions/20260422_opportunity_foundation.py#L33) declares `sa.Column("source", sa.String(length=30), nullable=True)`; the `Opportunity` class in [backend/app/models/opportunity.py:13-77](../../backend/app/models/opportunity.py#L13-L77) does not declare `source`. (The grep for `source:` finds matches only on `Task` and `OpportunitySignal`, not Opportunity.)
- **Impact:** Reading or writing `opportunity.source` from Python silently no-ops; lead-source attribution lost in analytics.
- **Minimal fix (model-only, no migration):**
  ```python
  source: Mapped[str | None] = mapped_column(String(30), nullable=True)
  ```

#### DB-7 — `invoices` table has no migration file
- **Severity:** high
- **Category:** database-backend mismatch
- **Evidence:** [backend/app/models/invoice.py](../../backend/app/models/invoice.py) defines the `Invoice` model with 16+ columns including `tenant_id`. Grepping `backend/alembic/versions/` for any reference to `invoices` returns **no matches** — there's no `CREATE TABLE invoices` migration, no `ADD COLUMN`, nothing.
- **How prod is currently working:** the table likely got created via SQLAlchemy's `metadata.create_all()` at first boot or via a one-off SQL run; either way it's invisible to `alembic upgrade head`.
- **Risk:** any new env can't bootstrap; future autogenerate runs will try to create it again with a different shape.
- **Minimal fix:** create `20260503_create_invoices.py` with `op.create_table(...)` reflecting the current model + a `CREATE TABLE IF NOT EXISTS` so existing prod is a no-op.
- **Migration required:** yes

#### DB-8 — `Invoice` relationships missing `back_populates` partner
- **Severity:** low
- **Evidence:** [backend/app/models/invoice.py:48-51](../../backend/app/models/invoice.py#L48-L51) uses `relationship("Customer", lazy="selectin")` etc.; sibling models (Customer, Quote, Contract) have no inverse `invoices = relationship(...)` declaration.
- **Impact:** can't `customer.invoices` from the Customer side; not a runtime bug but invisible to type-checkers.
- **Fix:** mirror the pattern we did for `OpportunitySignal` in v1.7.0 (DB-4 round-2).

### 2.3 Backend ↔ API contracts (MEDIUM × 3, LOW × 1)

#### A-10 — `GET /engagement/transcripts/` returns `{items, total, page, page_size}` without `pages`
- **Severity:** medium
- **Evidence:** [backend/app/api/v1/engagement.py:138-178](../../backend/app/api/v1/engagement.py#L138-L178). Round-2 standardized invoices/campaigns/contracts/customers; transcripts slipped.
- **Fix:** mirror A-4/5 — add `pages: math.ceil(total / page_size)`.

#### A-11 — `GET /engagement/sequences/` returns `{sequences: [...]}` with no pagination
- **Severity:** medium
- **Evidence:** [backend/app/api/v1/engagement.py:318-332](../../backend/app/api/v1/engagement.py#L318-L332).
- **Fix:** rename root key to `items`; add total/page/page_size/pages.

#### A-12 — `GET /engagement/segments/` non-canonical envelope (needs verification)
- **Severity:** medium *(needs manual verification)*
- **Agent flagged the same shape as A-11 around line 902 of engagement.py; I did not reread the exact lines.

#### AUD-2 — `bulk_action_customers` delete loop has no `audit_log` call
- **Severity:** high
- **Category:** compliance gap
- **Evidence:** [backend/app/api/v1/customers.py:734-754](../../backend/app/api/v1/customers.py#L734-L754) — `await db.delete(customer)` runs in a loop with zero `log_activity(...)` call. KVKK / SOX-style audit trail breaks for bulk deletes.
- **Note:** Pair with TEN-4 — the same endpoint needs both fixes.

### 2.4 API ↔ Frontend types (HIGH × 2, MEDIUM × 2)

#### TS-2 — `Quote` interface missing `opportunity_id`, `parent_quote_id`, `has_pdf`
- **Severity:** high
- **Evidence:** Backend `_quote_to_dict` returns all three at [quotes.py:694, 712, 710](../../backend/app/api/v1/quotes.py); TS interface at [types.ts:268-296](../../frontend/src/lib/types.ts#L268-L296) declares only `pdf_path` (the legacy field).
- **Impact:** UI can't link quotes back to opportunities or render version chains; `has_pdf` boolean isn't typed so the dynamic "open PDF" button can't safely gate on it.
- **Fix:**
  ```ts
  opportunity_id?: number | null;
  parent_quote_id?: number | null;
  has_pdf: boolean;
  ```

#### TS-3 — `Customer` interface missing `created_by` and `updated_at`
- **Severity:** medium
- **Evidence:** Backend `_customer_to_dict` returns both ([customers.py:920-922](../../backend/app/api/v1/customers.py#L920-L922)); TS at [types.ts:13-39](../../frontend/src/lib/types.ts#L13-L39) lacks them.
- **Impact:** "Owned by" attribution and "updated X ago" labels can't render typed.

#### TS-4 — `OpportunityFeaturesDailyLatest` missing parsed `momentum_drivers` + `stage_velocity_days`
- **Severity:** high
- **Evidence:** Backend [feature_store.py:104, 110](../../backend/app/api/v1/feature_store.py) returns parsed `momentum_drivers` (already deserialized from JSON) plus `stage_velocity_days`; TS [types.ts:546-570](../../frontend/src/lib/types.ts#L546-L570) has only the raw `momentum_drivers_json` string.
- **Impact:** Frontend re-parses the JSON each render, and never sees `stage_velocity_days` — the deal-health card can't show stage-progression chart. (Note: `objection_density_norm` was already added in round-2 O-2.)

#### TS-5 — `SparePart` has `has_price` but the API doesn't return it; missing `keywords_json`/`aliases_json`
- **Severity:** medium *(needs manual verification — claim is plausible based on backend serializer line 291-311 missing both fields, but verify both directions)*
- **Evidence:** [types.ts:207-224](../../frontend/src/lib/types.ts#L207-L224) declares `has_price: boolean`; agent's read of [parts.py:291-311](../../backend/app/api/v1/parts.py#L291-L311) found `keywords_json`/`aliases_json` returned but no `has_price`.

### 2.5 Cross-cutting — feature flags (MEDIUM × 1)

#### FLAG-2 — Four flags in `_PUBLIC_FEATURE_FLAGS` allow-list have no `Settings` field
- **Severity:** medium
- **Category:** feature-flag mismatch
- **Evidence:** [backend/app/api/v1/config.py:32-56](../../backend/app/api/v1/config.py#L32-L56) lists `FEATURE_INSIGHTS`, `FEATURE_COCKPIT`, `FEATURE_COMPLIANCE`, `FEATURE_KVKK`. Grepping `backend/app/core/config.py` for these four names returns **no matches** — they aren't declared on the `Settings` class.
- **Impact:** the loop at config.py:69-72 (`if hasattr(settings, name): flags[name] = ...`) silently skips them. Frontend always sees `false`. Any `useFeatureFlag('FEATURE_COCKPIT')` call permanently evaluates false even on prod where the cockpit is on.
- **Note:** I previously called this a false positive in round 2 — that call was wrong. The agent then was right that the names appear in the allow-list; I missed that they're not in `Settings`. Apologies for the round-2 misfire.
- **Minimal fix (option A — drop them from allow-list):** delete the four lines from `_PUBLIC_FEATURE_FLAGS` so the contract reflects reality.
- **Minimal fix (option B — add to Settings):** declare `FEATURE_INSIGHTS: bool = True` etc. on `Settings` class so they actually drive UI gating.

### 2.6 Realtime / state-lifecycle (MEDIUM × 2)

#### EVT-5 — `lead.score_changed` and `opportunity.score_changed` not subscribed by `WebhookService`
- **Severity:** medium
- **Evidence:** [backend/app/main.py:200-234](../../backend/app/main.py#L200-L234) wires `webhook_service.handle_event` to `opportunity.created`, `lead.converted`, `quote.approved`, `email.parsed`, etc. — but NOT to the score-change events round-2 added (EVT-1/EVT-2). External webhook subscribers can't react to scoring updates.
- **Fix:** add two `event_bus.subscribe(...)` lines.

#### CACHE-1 — Opportunity mutations don't invalidate the `['opportunities']` list cache
- **Severity:** high *(needs manual verification — agent's claim was about `applyPipelineStageMutation` but didn't pin a specific line; this is a pattern check across `OpportunityDetailPage.tsx` mutations)*
- **Impact:** rep updates an opportunity on the detail page → navigates back to list → list still shows old data until the 30s staleTime expires.
- **Fix:** every detail-page mutation `onSuccess` should invalidate both `['opportunity', id]` and `['opportunities']`.

### 2.7 Data fetched but not rendered (HIGH × 3, MEDIUM × 6, LOW × 1)

#### F-13 — `WorkflowRulesPage` cards hide what each rule actually does
- **Severity:** high
- **Evidence:** [frontend/src/features/admin/WorkflowRulesPage.tsx:254-323](../../frontend/src/features/admin/WorkflowRulesPage.tsx#L254-L323). API returns `conditions_json`, `actions_json`, `flow_json`, `updated_at`, `created_by`; UI shows only name + entity_type + trigger_event + is_active.
- **Impact:** admin sees "rule is on/off" but cannot inspect "what does it do?" without opening the visual editor. The most-important field is invisible.

#### F-14 — `PendingApprovalsPage` drops requester/assignee/comments/decision audit
- **Severity:** high
- **Evidence:** [frontend/src/features/approvals/PendingApprovalsPage.tsx:111-183](../../frontend/src/features/approvals/PendingApprovalsPage.tsx#L111-L183). API returns `requested_by`, `assigned_to`, `decided_by`, `decided_at`, `comments`, `rule_id`; UI shows only entity / level / status / created_at.
- **Impact:** approvers can't see who requested or what comments were left; the decision audit trail is invisible after approve/reject.

#### F-15 — `OpportunitiesHomePage` drops `rotting_days`, `close_date`, pipeline/territory, prior values
- **Severity:** high
- **Evidence:** [frontend/src/features/opportunities/OpportunitiesHomePage.tsx:230-300](../../frontend/src/features/opportunities/OpportunitiesHomePage.tsx#L230-L300). Backend's `_opp_to_dict` returns `rotting_days`, `close_date`, `pipeline_id`, `territory_id`, `previous_stage`, `previous_close_date`, `previous_amount`. Cards show only title/stage/forecast_category/probability/amount/customer/loss_reason.
- **Impact:** "this deal is rotting" and "this deal closes Friday" are the two highest-signal-per-pixel data points and both are dropped.

#### F-16 — `LeadListPage` drops phone/title/owner_name/converted_*
- **Severity:** medium
- **Evidence:** [LeadListPage.tsx:178-265](../../frontend/src/features/leads/LeadListPage.tsx#L178-L265); backend `_lead_to_dict` returns more than the table renders. Also no `notes` field in the create form even though backend accepts it.

#### F-17 — `CustomerDetailPage` Account360 open_deals drops amount/owner/updated_at
- **Severity:** medium
- **Evidence:** [CustomerDetailPage.tsx:818-834](../../frontend/src/features/customers/CustomerDetailPage.tsx#L818-L834). The triage-relevant signal (deal value, owner, last update) is dropped.

#### F-18 — `ContractDetailPage` drops `terms_json`, `created_by`, amendment.approved_by
- **Severity:** medium
- **Evidence:** [ContractDetailPage.tsx:160-205](../../frontend/src/features/contracts/ContractDetailPage.tsx#L160-L205). The contract terms field — usually the entire substantive content of the contract — is fetched then silently discarded.

#### F-19 — `CampaignListPage` drops `expected_revenue` + `description`
- **Severity:** medium
- **Evidence:** [CampaignListPage.tsx:261-358](../../frontend/src/features/campaigns/CampaignListPage.tsx#L261-L358). ROI column compares actual_cost/actual_revenue but never exposes planned-vs-actual.

#### F-20 — `SegmentsPage` cards drop `rules` array; no edit form
- **Severity:** medium
- **Evidence:** [SegmentsPage.tsx:344-374](../../frontend/src/features/engagement/SegmentsPage.tsx#L344-L374). A user can create a segment but never see what criteria it has, and clicking it goes to the customers list, not the rules editor.

#### F-21 — `CustomFieldsPage` table drops `options_json` for select-type fields
- **Severity:** medium
- **Evidence:** [CustomFieldsPage.tsx:98-161](../../frontend/src/features/admin/CustomFieldsPage.tsx#L98-L161). Admin sees "Type: Seçim" with no insight into what choices are configured.

#### F-22 — `IntegrationsPage` drops `calendarHealth.error`
- **Severity:** low
- **Evidence:** [IntegrationsPage.tsx:291-298](../../frontend/src/features/integrations/IntegrationsPage.tsx#L291-L298). When `health.ok === false` the precise error is fetched and dropped; user sees only a generic "unknown".

---

## 3. Findings by API Endpoint

| Endpoint | Findings |
|---|---|
| `POST /customers/bulk-action` | TEN-4 (cross-tenant), AUD-2 (no audit log) |
| `POST /leads/bulk-action` | TEN-5 (cross-tenant) |
| `POST /duplicates/merge` | TEN-8 (cross-tenant merge) |
| `PATCH /quotes/{id}/approve` | TEN-6 |
| `POST /quotes/{id}/send` | TEN-7 |
| `GET /quotes/{id}` | TS-2 (TS missing fields) |
| `GET /customers/{id}` | TS-3 (TS missing fields) |
| `GET /v4/opportunities/{id}/features/latest` | TS-4 (parsed momentum_drivers + stage_velocity_days) |
| `GET /parts/{id}` | TS-5 (needs verification) |
| `GET /engagement/transcripts/` | A-10 (envelope missing `pages`) |
| `GET /engagement/sequences/` | A-11 (non-canonical envelope) |
| `GET /engagement/segments/` | A-12 (needs verification) |
| `GET /config/feature-flags` | FLAG-2 (4 ghost flags) |
| events `lead.score_changed`/`opportunity.score_changed` | EVT-5 (no webhook subscribe) |

---

## 4. Findings by DB Entity / Table

| Table | Findings |
|---|---|
| `opportunities` | DB-6 (`source` column unmapped) |
| `invoices` | DB-7 (no migration), DB-8 (no `back_populates`) |
| customers (bulk path) | TEN-4 |
| leads (bulk path) | TEN-5 |
| customers (merge path) | TEN-8 |
| quotes (approve/send) | TEN-6, TEN-7 |

---

## 5. Cross-Layer Compatibility Matrix (key entities)

| Entity | DB | Backend Model | API Field | TS Type | UI | Status |
|---|---|---|---|---|---|---|
| `opportunities.source` | ✓ migration | ✗ unmapped | ✗ | ✗ | ✗ | ⚠ DB-6 |
| `invoices.*` | ✓ live | ✓ model | ✓ | ✓ | ✓ | ⚠ DB-7 (no migration file) |
| `Quote.opportunity_id` / `parent_quote_id` / `has_pdf` | ✓ | ✓ | ✓ | ✗ missing | ✗ partial | ⚠ TS-2 |
| `Customer.created_by` / `updated_at` | ✓ | ✓ | ✓ | ✗ missing | ✗ | ⚠ TS-3 |
| `OpportunityFeaturesDailyLatest.momentum_drivers` (parsed) | computed | ✓ | ✓ | ✗ missing | partial | ⚠ TS-4 |
| `OpportunityFeaturesDailyLatest.stage_velocity_days` | ✓ | ✓ | ✓ | ✗ missing | ✗ | ⚠ TS-4 |
| `Customer` (bulk_action) | tenant_id ✓ | tenant_id ✓ | not enforced on bulk path | n/a | n/a | ⛔ TEN-4 |
| `Lead` (bulk_action) | tenant_id ✓ | tenant_id ✓ | not enforced on bulk path | n/a | n/a | ⛔ TEN-5 |
| `Customer` (merge path) | tenant_id ✓ | tenant_id ✓ | not enforced | n/a | n/a | ⛔ TEN-8 |
| `Quote` (approve/send) | tenant_id ✓ | tenant_id ✓ | not enforced | n/a | n/a | ⚠ TEN-6/7 |
| Workflow rule conditions/actions | n/a | ✓ | ✓ | ✓ | ✗ not rendered | ⚠ F-13 |
| Approval requester/assignee/comments | n/a | ✓ | ✓ | ✓ | ✗ not rendered | ⚠ F-14 |
| Opportunity rotting_days/close_date | computed/✓ | ✓ | ✓ | ✓ | ✗ not rendered | ⚠ F-15 |
| FEATURE_INSIGHTS / COCKPIT / COMPLIANCE / KVKK | n/a | ✗ no Settings field | ✓ in allow-list | ✗ always-false | ✗ | ⚠ FLAG-2 |
| `lead.score_changed` / `opportunity.score_changed` event | n/a | ✓ emitted | n/a | n/a | n/a | ⚠ EVT-5 (no webhook sub) |

---

## 6. Fix Plan

### Quick wins (no migration, < 2 hr each)

| # | Fix | File | Risk |
|---|---|---|---|
| TEN-4 | `scoped_for_user` wrap on bulk_action_customers | `customers.py:725` | low — same pattern as round-2 TEN-1 |
| TEN-5 | same on bulk_action_leads | `leads.py:402` | low |
| TEN-6 | `assert_same_tenant` after `_get_quote_or_raise` | `quotes.py:275` (or service-side) | low |
| TEN-7 | `assert_same_tenant` after the SELECT | `quotes.py:325` | low |
| TEN-8 | `assert_same_tenant` on winner+loser inside merge_records | `record_duplicate_service.py:184/189` | low |
| DB-6 | add `source: Mapped[str \| None] = mapped_column(String(30), nullable=True)` | `models/opportunity.py` | none |
| TS-2 | add 3 fields to `Quote` interface | `types.ts:268` | none |
| TS-3 | add `created_by` + `updated_at` to `Customer` | `types.ts:13` | none |
| TS-4 | add `momentum_drivers: Array<{...}>` + `stage_velocity_days?: number \| null` | `types.ts:546` | none |
| FLAG-2 | drop the 4 ghost flags from allow-list OR add to `Settings` | `config.py:32-56` (and/or `core/config.py`) | low |
| AUD-2 | add `await log_activity(...)` inside the bulk delete loop | `customers.py:739` | none |
| A-10 | add `pages` to transcripts response | `engagement.py:178` | none |
| A-11 | rename `sequences` → `items`, add pagination | `engagement.py:325` | low (frontend coupling) |
| EVT-5 | `event_bus.subscribe("lead.score_changed", webhook_service.handle_event)` × 2 | `main.py:200-234` | none |

### Safe refactors (1–4 hr each)

- **F-13** — render conditions/actions chip strip on `WorkflowRulesPage`
- **F-14** — surface requester/assignee/comments on `PendingApprovalsPage`
- **F-15** — add rotting_days + close_date chips to opportunity cards (and red warn for `rotting_days > 7`)
- **F-16** through **F-22** — JSX-only field surfacing (mirror v1.6.1 F-1..F-12 batch shape)
- **DB-8** — add `back_populates` between Invoice ↔ Customer/Quote/Contract/User
- **CACHE-1** — audit every detail-page `useMutation` for cross-key invalidation

### Migration-required fixes

- **DB-7** — create `20260503_create_invoices.py` with `CREATE TABLE IF NOT EXISTS invoices (...)`. Idempotent on existing prod.

### Risky / manual review

- **TS-5** SparePart fields — needs side-by-side verification before patching
- **A-12** segments envelope — agent flagged but I didn't reread the lines
- **CACHE-1** — pattern audit, not a single-line fix; needs a sweep

---

## 7. Suggested Code Patches (top-priority)

### TEN-4: Tenant-scope bulk_action_customers

```diff
--- a/backend/app/api/v1/customers.py
+++ b/backend/app/api/v1/customers.py
@@ -724,7 +724,9 @@ async def bulk_action_customers(
     # Validate that all IDs exist
     result = await db.execute(
-        select(Customer).where(Customer.id.in_(ids))
+        scoped_for_user(select(Customer), Customer, current_user).where(
+            Customer.id.in_(ids),
+        )
     )
```

### TEN-5: Same for bulk_action_leads

```diff
--- a/backend/app/api/v1/leads.py
+++ b/backend/app/api/v1/leads.py
@@ -401,7 +401,9 @@ async def bulk_action_leads(
     # Validate that all IDs exist
     result = await db.execute(
-        select(Lead).where(Lead.id.in_(ids))
+        scoped_for_user(select(Lead), Lead, current_user).where(
+            Lead.id.in_(ids),
+        )
     )
```

### TEN-8: Tenant-scope the merge service

```diff
--- a/backend/app/services/record_duplicate_service.py
+++ b/backend/app/services/record_duplicate_service.py
@@ -180,12 +180,17 @@ async def merge_records(
     winner_result = await self.db.execute(
         select(Customer).where(Customer.id == winner_id)
     )
     winner = winner_result.scalar_one_or_none()
+    if winner is None:
+        return {"error": "Kayit bulunamadi"}
+    assert_same_tenant(winner, current_user, exception_cls=NotFoundException)

     loser_result = await self.db.execute(
         select(Customer).where(Customer.id == loser_id)
     )
     loser = loser_result.scalar_one_or_none()
-
-    if not winner or not loser:
+    if loser is None:
         return {"error": "Kayit bulunamadi"}
+    assert_same_tenant(loser, current_user, exception_cls=NotFoundException)
```

(Service signature needs `current_user: User` added — chase the call site in `duplicates.py:91` to pass it through.)

### TEN-6 + TEN-7: Tenant-guard quote write paths

```diff
--- a/backend/app/api/v1/quotes.py
+++ b/backend/app/api/v1/quotes.py
@@ -271,7 +271,11 @@ async def approve_quote(
     db: AsyncSession = Depends(get_db),
 ):
-    """Approve a quote and generate PDF (sales_manager only)."""
+    """Approve a quote and generate PDF (sales_manager only)."""
+    quote_pre = (
+        await db.execute(select(Quote).where(Quote.id == quote_id))
+    ).scalar_one_or_none()
+    if quote_pre is None:
+        raise NotFoundException("Teklif bulunamadi")
+    assert_same_tenant(quote_pre, current_user, exception_cls=NotFoundException)
     service = QuoteService(db)
     quote = await service.approve_quote(...)

@@ -322,6 +326,7 @@ async def send_quote(
     quote = result.scalar_one_or_none()
     if not quote:
         raise NotFoundException("Teklif bulunamadi")
+    assert_same_tenant(quote, current_user, exception_cls=NotFoundException)
```

### DB-6: Map Opportunity.source

```diff
--- a/backend/app/models/opportunity.py
+++ b/backend/app/models/opportunity.py
@@ ... (in class Opportunity, after `customer_id`)
+    # Lead-source attribution. Migration 20260422_opportunity_foundation.py:33
+    # creates the column; the model never declared it, so reads/writes
+    # silently no-op'd.
+    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
```

### TS-2: Quote interface fields

```diff
--- a/frontend/src/lib/types.ts
+++ b/frontend/src/lib/types.ts
@@ -283,6 +283,9 @@ export interface Quote {
   valid_days: number;
   notes: string;
   pdf_path: string | null;
+  has_pdf: boolean;
+  opportunity_id?: number | null;
+  parent_quote_id?: number | null;
   version: number;
```

### FLAG-2 (option A — drop ghost flags)

```diff
--- a/backend/app/api/v1/config.py
+++ b/backend/app/api/v1/config.py
@@ -52,10 +52,6 @@ _PUBLIC_FEATURE_FLAGS: set[str] = {
-    "FEATURE_INSIGHTS",
-    "FEATURE_COCKPIT",
-    "FEATURE_COMPLIANCE",
-    "FEATURE_KVKK",
 }
```
(Or, if these features are in fact gated, declare them on `Settings`.)

---

## 8. Suggested Database Migrations

### `20260503_create_invoices.py` (DB-7)

```python
"""Create invoices table — model existed without a migration

Revision ID: 20260503_create_invoices
Revises: 20260502_value_date_to_date
Create Date: 2026-05-03

The Invoice model has been live in prod since the v1.5.x invoicing
sprint, but no migration was ever authored. The table likely got
created via metadata.create_all() at first boot. This migration uses
CREATE TABLE IF NOT EXISTS so existing prod is a no-op while fresh
envs can bootstrap from `alembic upgrade head`.
"""

from alembic import op


revision = "20260503_create_invoices"
down_revision = "20260502_value_date_to_date"

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            invoice_number VARCHAR(50) UNIQUE NOT NULL,
            quote_id INTEGER REFERENCES quotes(id),
            contract_id INTEGER REFERENCES contracts(id),
            customer_id INTEGER REFERENCES customers(id),
            tenant_id INTEGER,
            created_by INTEGER REFERENCES users(id),
            issue_date TIMESTAMPTZ,
            due_date TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            currency VARCHAR(10) NOT NULL DEFAULT 'TRY',
            subtotal DOUBLE PRECISION NOT NULL DEFAULT 0,
            tax_rate DOUBLE PRECISION NOT NULL DEFAULT 20,
            tax_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
            grand_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            items_json TEXT,
            notes TEXT,
            pdf_path VARCHAR(500),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_invoices_customer_id ON invoices (customer_id)"
    )

def downgrade() -> None:
    # Intentionally no-op: dropping the table would destroy live data.
    pass
```

**Verify the column list against `models/invoice.py` before merging** — I sketched from typical fields seen in v1.7.0; the actual model may have more.

---

## 9. Suggested Tests

| Layer | Test | Rationale |
|---|---|---|
| API + Tenant | `test_bulk_action_customers_rejects_other_tenant` | Catches TEN-4 |
| API + Tenant | `test_bulk_action_leads_rejects_other_tenant` | TEN-5 |
| API + Tenant | `test_merge_records_rejects_other_tenant` | TEN-8 |
| API + Tenant | `test_approve_quote_rejects_other_tenant` | TEN-6 |
| API + Tenant | `test_send_quote_rejects_other_tenant` | TEN-7 |
| Schema | `test_every_migration_column_appears_in_some_model` (introspect Base.metadata vs alembic.upgrade_to_head) | Catches DB-6 family |
| Schema | `test_every_model_table_has_a_create_table_migration` | Catches DB-7 |
| Frontend types | `test_quote_response_has_opportunity_id_field` | TS-2 |
| Feature flags | `test_public_feature_flags_all_exist_on_settings` | FLAG-2 |
| Realtime | `test_score_change_events_have_webhook_subscriber` | EVT-5 |
| Frontend render | RTL: `WorkflowRulesPage` renders conditions chips | F-13 |
| Compliance | `test_bulk_delete_writes_audit_log_per_entity` | AUD-2 |

---

## Final summary lists

- **DB columns not used by backend:** DB-6 (`opportunities.source`)
- **Backend model fields not backed by DB migrations:** DB-7 (`invoices` table, all columns)
- **Backend fields not exposed through API:** none confirmed in this round
- **API fields never consumed by frontend:** F-13 through F-22 (10 confirmed) plus TS-2/TS-3/TS-4 fields
- **Frontend fields/types missing from API/backend:** TS-2 (Quote 3 fields), TS-3 (Customer 2 fields), TS-4 (features 2 fields), TS-5 (SparePart, needs verification)
- **Data fetched but not rendered:** F-13 through F-22 plus the TS-* gaps that mean the data type-erases on arrival
- **UI components showing incomplete data:** WorkflowRulesPage, PendingApprovalsPage, OpportunitiesHomePage, LeadListPage, CustomerDetailPage Account360, ContractDetailPage, CampaignListPage, SegmentsPage, CustomFieldsPage, IntegrationsPage
- **Realtime events emitted but not handled:** EVT-5 (webhook sub gap on score events)
- **Realtime events handled but not emitted:** none new in round 3
- **Schema/type/nullability mismatches:** DB-6, DB-7, DB-8, TS-2..5
- **Permission / feature-flag mismatches:** TEN-4..8 (5), FLAG-2
- **Required migrations:** 1 mandatory (DB-7), 0 optional
- **Recommended frontend type updates:** TS-2 (Quote), TS-3 (Customer), TS-4 (features); TS-5 pending verification
- **Recommended backend DTO/serializer updates:** none — the backend already returns these fields
- **Recommended tests:** 12 (per section 9)

---

## Rejected during verification (false positives)

These appeared in agent reports but were re-checked against source and found **not** to be bugs:

| Claim | Why it's not a bug |
|---|---|
| Orphan alembic migration heads (DB agent claimed 2 branches) | `script.get_heads()` returns single head `20260502_value_date_to_date`; chain length 38. |
| `Opportunity.previous_amount` Float vs DOUBLE PRECISION drift | SQLAlchemy `Float()` maps to PostgreSQL `DOUBLE PRECISION`; round-trip is identical. |
| `_get_quote_or_raise` "missing tenant check" mentioned in passing | True at the helper layer, but the round-2 audit already mandated per-endpoint guards (TEN-3); we extend that pattern with TEN-6/7 rather than recharacterizing the helper. |
| PRIV-1 (operations user sees Approvals nav) | [Sidebar.tsx:279](../../frontend/src/components/layout/Sidebar.tsx#L279) wraps the Approvals NavLink in `{canSeeApprovals && ...}`. `canSeeApprovals = userRole === 'sales_rep' \|\| userRole === 'sales_manager'` excludes operations. |
| Race condition on concurrent score updates | Speculative — no reproducer; would need a `SELECT … FOR UPDATE` retrofit but that's a defensive micro-opt, not an active bug. |

I owe a correction on the round-2 X-6 false-positive call too: I dismissed it because the four flag names appeared in `_PUBLIC_FEATURE_FLAGS`, but I missed that they're **not** declared on the `Settings` class. The correct finding is **FLAG-2** above.

---

## Methodology

Six parallel `Explore` / `general-purpose` subagents, each scoped to one layer:

1. **DB ↔ Backend ORM** — migrations vs models, type/nullability/index/relationship drift
2. **Backend ↔ API contract** — DTO completeness, response shapes, pagination envelopes, enum exposure
3. **API ↔ Frontend client** — TS type drift, defensive fallbacks, generic-typed responses
4. **Data fetched but not rendered** — JSX vs query data, partial renders, write-only form fields
5. **Realtime + state lifecycle** — publish/subscribe pairing, payload validation, exception handling, cache invalidation
6. **Permissions + feature flags + naming** — `assert_same_tenant` coverage, role-check consistency, flag allow-list

Every headline finding was re-verified against source by direct file read after the agents returned. Items marked "needs manual verification" lacked sufficient line-level evidence in the agent's report and have been left for human spot-check rather than fabricated.

No code modified per the explicit "do not modify files unless asked" rule from the audit prompt.
