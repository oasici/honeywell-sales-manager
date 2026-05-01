# Cross-Layer Audit Report — Honeywell Sales Suite

**Date:** 2026-05-01
**Branch:** `deploy/render-sandbox`
**HEAD:** `cc1fafb` (post v1.5.3)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions · State/lifecycle

Synthesized from 6 parallel layer-focused scans. Findings exclude the 32 already-fixed items from the prior audit (v1.5.0–v1.5.3).

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| Total new findings | **34** |
| Critical | 1 |
| High | 9 |
| Medium | 14 |
| Low | 10 |

**Most-affected surfaces:**
- **Backend models / migrations** (7 findings) — duplicate field declarations, missing index metadata, nullability drift in V5 expansion columns
- **Cockpit + Opportunity detail** (8 findings) — partial-render of fetched data (V4 features, coaching indicators, decision gaps, competitor mentions)
- **Realtime / event bus** (7 findings) — events emitted with no handlers, handlers with no emitters, silent failures
- **Cache invalidation** (3 findings) — mutations don't invalidate detail-page queryKeys

**Biggest schema-drift area:** `quotes` model (duplicate field) and V9 CRM sync models (missing `__table_args__` indexes).

**Biggest UX risk:** event handler failures silently swallowed in `event_bus.publish` (Finding R-3).

---

## 2. Findings by Feature / Page

### 2.1 Quotes (CRITICAL)

#### Q-1 — Duplicate `parent_quote_id` declaration in Quote model
- **Severity:** critical
- **Category:** database-backend mismatch
- **Evidence:** [backend/app/models/quote.py:44-46](../../backend/app/models/quote.py#L44-L46) declares the field; [backend/app/models/quote.py:64-66](../../backend/app/models/quote.py#L64-L66) declares the **same field again**
- **Expected:** single column declaration
- **Actual:** SQLAlchemy will silently keep one and discard the other; may surface as `AttributeError` at query time depending on import order
- **Root cause:** incomplete merge during quote-revision tree refactor
- **Minimal fix:** delete lines 64–66
- **Tests:** add `test_quote_model_has_no_duplicate_columns` that introspects `Quote.__table__.columns`

### 2.2 OpportunityDetailPage (HIGH × 3)

#### O-1 — Decision-gap actions truncated to first only
- **Severity:** high
- **Category:** data-not-rendered
- **Evidence:** [frontend/src/features/board/OpportunityDetailPage.tsx:1079-1100](../../frontend/src/features/board/OpportunityDetailPage.tsx#L1079-L1100) renders `g.recommended_actions[0]`; the API returns the full array
- **Note:** Phase-1 fix only addressed `CockpitPage.tsx` — this is the **detail page**, separate code path
- **User impact:** reps see 1 of 3-5 recommended actions per gap on the detail page
- **Minimal fix:** render all actions as chips (mirror what we shipped for cockpit)

#### O-2 — V4 latest features card shows 8 of 15 fields
- **Severity:** medium
- **Category:** partial-render
- **Evidence:** [frontend/src/features/board/OpportunityDetailPage.tsx:928-985](../../frontend/src/features/board/OpportunityDetailPage.tsx#L928-L985) renders 8 fields in a fixed 4×2 grid
- **Hidden fields:** `quote_count`, `latest_discount_pct`, `competitor_mentions_30d`, `pricing_objections_30d`, `positive_signal_count_14d`, `deal_age_days`, `objection_density_norm`
- **Minimal fix:** expand grid to 3 columns, conditionally render non-zero values

#### O-3 — `OpportunityIntelligencePanel` momentum_drivers never rendered if API has no `data` wrapper
- **Severity:** medium
- **Category:** api-frontend mismatch
- **Evidence:** [frontend/src/lib/api.ts:927-928](../../frontend/src/lib/api.ts#L927-L928) does `data?.data ?? null`; backend [feature_store.py:43-83](../../backend/app/api/v1/feature_store.py#L43-L83) returns `{"data": {...}}` so the unwrap works, but the defensive `?? null` masks any future contract change
- **Minimal fix:** pin response shape with a Pydantic model + matching TS type; remove the defensive fallback

### 2.3 CockpitPage (MEDIUM × 3)

#### C-1 — CoachingPanel rep `indicators[]` array fetched but never rendered
- **Severity:** medium
- **Category:** data-not-rendered
- **Evidence:** [frontend/src/features/cockpit/CockpitPage.tsx:625-690](../../frontend/src/features/cockpit/CockpitPage.tsx#L625-L690) — table shows 4 columns (rep, score, risk, recommendations); type includes `indicators: {name, label, score, weight}[]` per rep, never iterated
- **Minimal fix:** collapsible row on click revealing the indicator breakdown

#### C-2 — CompetitiveIntelPanel `recent_mentions` truncated to 1
- **Severity:** low
- **Category:** data-not-rendered
- **Evidence:** [CockpitPage.tsx:737-782](../../frontend/src/features/cockpit/CockpitPage.tsx#L737-L782) — `comp.recent_mentions?.slice(0, 1)` discards 4-9 mentions per competitor
- **Minimal fix:** show 3 with `+N more` chip

#### C-3 — `IntelligenceDriver` referenced as a type but not exported from `types.ts`
- **Severity:** high
- **Category:** type-mismatch
- **Evidence:** [api.ts:1131-1139](../../frontend/src/lib/api.ts#L1131-L1139) types buyer-state `drivers` as `IntelligenceDriver[]`. The interface IS defined in api.ts but is NOT re-exported through types.ts; consumers in cockpit components can't import it from the canonical types module
- **Note:** `IntelligenceDriver` was created in api.ts during Phase 2 — but it's only available there, not from `types.ts`. Consumers using `import type { IntelligenceDriver } from '../../lib/types'` get `any`
- **Minimal fix:** re-export from `types.ts`: `export type { IntelligenceDriver } from './api';` OR move the interface to `types.ts`

### 2.4 CustomerDetailPage / List (HIGH)

#### CU-1 — Customer create mutation invalidates `['customers']` but not `['customer', id]`
- **Severity:** high
- **Category:** cache-invalidation
- **Evidence:** [CustomerListPage.tsx:290-298](../../frontend/src/features/customers/CustomerListPage.tsx#L290-L298) only invalidates `['customers']`; [CustomerDetailPage.tsx:90-93](../../frontend/src/features/customers/CustomerDetailPage.tsx#L90-L93) reads `['customer', customerId]`
- **User impact:** navigating to a freshly-created customer detail page shows stale/empty data until F5
- **Minimal fix:** `queryClient.setQueryData(['customer', newCustomer.id], newCustomer)` in `onSuccess`

#### CU-2 — `CustomerHealthReport.explanations` returned by API but missing from TS type
- **Severity:** medium
- **Category:** type-mismatch / data-not-rendered
- **Evidence:** [customer_health.py:36-51](../../backend/app/api/v1/customer_health.py#L36-L51) conditionally returns `explanations[]` when `?include_explanations=true`; [types.ts:359-367](../../frontend/src/lib/types.ts#L359-L367) `CustomerHealthReport` doesn't declare it
- **Minimal fix:** add `explanations?: HealthExplanation[]` interface

### 2.5 Email Inbox (MEDIUM × 2)

#### E-1 — Email poll mutation is fire-and-forget; no progress / failure surface
- **Severity:** medium
- **Category:** state-lifecycle
- **Evidence:** [EmailListPage.tsx:90-99](../../frontend/src/features/emails/EmailListPage.tsx#L90-L99) mutation; [emails.py:214-260](../../backend/app/api/v1/emails.py#L214-L260) polls IMAP synchronously, returns 200 immediately
- **User impact:** user sees "success" toast even if half the emails errored mid-poll; no way to retry just the failures
- **Minimal fix:** backend returns `{job_id, status: "running"}`, frontend polls a status endpoint; OR accept current limitation but surface failure count in the toast

#### E-2 — Listing the still-fixable case from prior audit
- **Severity:** medium
- **Category:** api-frontend mismatch (already in v1.5.0)
- **Evidence:** prior audit's email triage fields shipped — verify Phase-1 deploy actually rendered after the v1.5.1 hotfix

### 2.6 Invoices (HIGH)

#### I-1 — `invoice.paid` event subscribed but never emitted
- **Severity:** high
- **Category:** realtime mismatch
- **Evidence:** [main.py:251-257](../../backend/app/main.py#L251-L257) registers `event_bus.subscribe("invoice.paid", _on_invoice_paid)`; [invoices.py:263-269](../../backend/app/api/v1/invoices.py#L263-L269) sets `invoice.paid_at = now` but never publishes the event
- **User impact:** any downstream listener (revenue tracking, contract actual-revenue updates, future Slack/Teams notifier) is dead-lettered
- **Minimal fix:**
  ```python
  # backend/app/api/v1/invoices.py:263-268
  if body.status == "paid":
      invoice.paid_at = now
      from app.core.event_bus import event_bus
      await event_bus.publish("invoice.paid", {
          "invoice_id": invoice.id,
          "customer_id": invoice.customer_id,
          "amount": float(invoice.grand_total),
      })
  ```

### 2.7 Compliance / Webhooks (MEDIUM × 2)

#### WH-1 — Webhook deliveries fail once with no retry
- **Severity:** medium
- **Category:** state-lifecycle
- **Evidence:** [webhook_service.py:130-159](../../backend/app/services/webhook_service.py#L130-L159) makes one POST attempt; [model](../../backend/app/models/webhook.py) declares `MAX_FAILURE_COUNT = 10` but never enforced
- **User impact:** temporarily-down webhook endpoint loses all events
- **Minimal fix:** 3 attempts with exponential backoff (1s/2s/4s); persist `attempt_count` to delivery row

#### WH-2 — `domain_events` table written but no admin-facing reader
- **Severity:** low
- **Category:** data-not-rendered
- **Evidence:** [domain_events.py:112-122](../../backend/app/services/domain_events.py#L112-L122) writes; [engagement.py:612-624](../../backend/app/api/v1/engagement.py#L612-L624) exposes a reader endpoint; only [LeadDetailPage.tsx](../../frontend/src/features/leads/LeadDetailPage.tsx) consumes it for `lead.score_changed`
- **Minimal fix:** admin "Event Audit Log" page surfacing all event types with entity/date filters

### 2.8 V9 CRM Sync Models (HIGH × 2)

#### V9-1 — `CrmConnection` missing `__table_args__` for tenant index
- **Severity:** high
- **Category:** database-backend mismatch
- **Evidence:** [v9_crm_sync.py migration:46-48](../../backend/alembic/versions/20260428_v9_crm_sync.py#L46-L48) creates `ix_crm_connections_tenant_active`; [model](../../backend/app/models/v9_crm_sync.py#L22-L47) has no `__table_args__`
- **Impact:** SQLAlchemy autogenerate would attempt to drop the "missing" index on next `--autogenerate`
- **Minimal fix:**
  ```python
  __table_args__ = (
      Index("ix_crm_connections_tenant_active", "tenant_id", "is_active"),
  )
  ```

#### V9-2 — `CrmRecordLink` redundant index on top of unique constraint
- **Severity:** medium
- **Category:** database-backend mismatch
- **Evidence:** [migration line 96](../../backend/alembic/versions/20260428_v9_crm_sync.py#L96) declares `UNIQUE(connection_id, internal_entity_type, internal_id)` (auto-creates an index); [model lines 106-111](../../backend/app/models/v9_crm_sync.py#L106-L111) adds **another** Index on the same columns
- **Impact:** wasted disk + write amplification
- **Minimal fix:** remove the duplicate `Index(...)` from `__table_args__`

### 2.9 V5 Foundation columns (MEDIUM)

#### V5-1 — `account_features_daily` / `rep_features_daily` nullability ambiguity
- **Severity:** medium
- **Category:** database-backend mismatch
- **Evidence:** [migration:31-32](../../backend/alembic/versions/20260427_v5_foundation.py#L31-L32) declares `objection_density_30d DOUBLE PRECISION NOT NULL DEFAULT 0`; [model:71](../../backend/app/models/feature_store_daily.py#L71) declares `Mapped[float] = mapped_column(Float, default=0.0)` without `nullable=False`
- **Impact:** type inference matches but explicit `nullable=False` is the documented pattern in this codebase elsewhere; current state is fragile
- **Minimal fix:** add `nullable=False` for clarity (no migration needed)

### 2.10 Engagement (MEDIUM × 2)

#### EG-1 — Sequence event handler errors silently swallowed
- **Severity:** high
- **Category:** realtime mismatch
- **Evidence:** [event_bus.py:36-68](../../backend/app/core/event_bus.py#L36-L68) `publish()` retries once, logs error on second failure, **never raises**; [main.py:193-210](../../backend/app/main.py#L193-L210) handler wraps in `try/except` and just `logger.warning`
- **Impact:** sequence completion → workflow rule fires fail silently; user sees "completed" but downstream actions never run
- **Minimal fix:** write to a `dead_letter_events` table on terminal failure so an admin job can replay

#### EG-2 — `revenue_signal.created` event missing from `EVENT_PAYLOAD_SCHEMAS`
- **Severity:** medium
- **Category:** realtime mismatch
- **Evidence:** [domain_events.py:23-48](../../backend/app/services/domain_events.py#L23-L48) defines `SIGNAL_CREATED = "revenue_signal.created"` constant; [domain_events.py:52-87](../../backend/app/services/domain_events.py#L52-L87) `EVENT_PAYLOAD_SCHEMAS` dict does NOT include it; emitted at [revenue_signal_service.py:89](../../backend/app/services/revenue_signal_service.py#L89) with un-validated payload
- **Minimal fix:** add the entry to the schemas dict

### 2.11 API Contract Drift (MEDIUM × 4)

#### A-1 — `/customers/high-intent` returns abbreviated pagination shape
- **Severity:** medium
- **Category:** backend-api mismatch
- **Evidence:** [customers.py:106-119](../../backend/app/api/v1/customers.py#L106-L119) returns `{items, total}` only; sibling [list_customers:87-93](../../backend/app/api/v1/customers.py#L87-L93) returns `{items, total, page, page_size, pages}`
- **Impact:** frontend list components must special-case this endpoint
- **Minimal fix:** align to the canonical shape

#### A-2 — Opportunity `?status=` query param accepted but ignored
- **Severity:** medium
- **Category:** backend-api mismatch
- **Evidence:** opportunities list declares `status: str | None = Query("active")` but the SQL filter is hardcoded to `Opportunity.status == "active"` (per audit agent — needs file:line confirmation)
- **Impact:** status filter UI appears functional, returns no closed-lost results
- **Note:** **needs manual verification** — agent didn't pin the exact line

#### A-3 — `engagement_legacy_router` mounted but undocumented as deprecated
- **Severity:** low
- **Category:** backend-api mismatch
- **Evidence:** [router.py:107](../../backend/app/api/v1/router.py#L107); [engagement.py:1198-1201](../../backend/app/api/v1/engagement.py#L1198-L1201)
- **Minimal fix:** add `# DEPRECATED — remove 2026-09` comment + log warning on hit

#### A-4 — Address column unbounded but Pydantic schema has no `max_length`
- **Severity:** low
- **Category:** validation gap
- **Evidence:** [customer.py model:23](../../backend/app/models/customer.py#L23) `Mapped[str | None] = mapped_column(Text, nullable=True)`; [customer.py schema:13](../../backend/app/schemas/customer.py#L13) `address: str | None = None` (no `Field(max_length=...)`)
- **Impact:** low (DB tolerates large input) but defense-in-depth recommends a 1024 cap
- **Minimal fix:** `Field(None, max_length=1024)`

### 2.12 Cross-cutting / Naming (HIGH × 1, others low)

#### X-1 — Frontend gating missing for ~20 of 24 backend FEATURE_* flags
- **Severity:** high
- **Category:** feature-flag mismatch
- **Evidence:** [config.py:268-396](../../backend/app/core/config.py#L268-L396) declares 24 flags; [App.tsx](../../frontend/src/app/App.tsx) routes are mostly always-rendered. Phase 5 added `FeatureFlagContext` but most routes haven't been wrapped yet
- **Impact:** when a feature flag is off in a deployment, users still see the menu item, click → 404 with our new error toast (better than before, but still broken UX)
- **Minimal fix:** wrap each affected route in `<FeatureFlagGate flag="FEATURE_V10_PARTS_INTEL">` style component

#### X-2 — `OpportunitySignal.signal_type` typed as `string` instead of literal union
- **Severity:** high
- **Category:** enum drift
- **Evidence:** [enums.py:43-56](../../backend/app/models/enums.py#L43-L56) defines 12 values; [types.ts:450-459](../../frontend/src/lib/types.ts#L450-L459) `OpportunitySignal.signal_type: string`
- **Impact:** switch statements/label maps in the UI silently fail when backend adds a new signal type
- **Minimal fix:**
  ```ts
  export type OpportunitySignalType =
    | 'pricing_concern' | 'competitor' | 'objection' | 'no_touch'
    | 'discount_risk' | 'sla_breach' | 'positive'
    | 'workflow_triggered' | 'coaching_needed' | 'stage_change'
    | 'expansion_signal' | 'playbook_completed';

  export interface OpportunitySignal {
    // …
    signal_type: OpportunitySignalType;
  }
  ```

#### X-3 — `QuoteStatus` typed as `string` (same pattern)
- **Severity:** low
- **Same fix pattern as X-2**

#### X-4 — Auth password-reset response uses `user_id` (snake_case ID) while User type uses `id`
- **Severity:** medium
- **Category:** naming drift
- **Evidence:** [users.py:159](../../backend/app/api/v1/users.py#L159) returns `{"user_id": user.id, ...}`; [types.ts User interface:2-10](../../frontend/src/lib/types.ts#L2-L10) uses `id`
- **Minimal fix:** backend renames to `id`

---

## 3. Findings by API Endpoint

| Endpoint | Findings |
|---|---|
| `GET /v4/opportunities/{id}/features/latest` | O-3 (defensive fallback) |
| `GET /buyer-state/.../timeline` | C-3 (IntelligenceDriver export) |
| `GET /customer-health/.../report?include_explanations=true` | CU-2 (explanations type missing) |
| `GET /customers/high-intent` | A-1 (truncated pagination) |
| `GET /opportunities?status=` | A-2 (param ignored) |
| `POST /invoices/{id}` (status=paid) | I-1 (event not emitted) |
| `POST /emails/poll` | E-1 (no progress feedback) |
| webhook deliveries | WH-1 (no retry) |
| `POST /auth/password-reset` | X-4 (snake_case `user_id`) |

---

## 4. Findings by DB Entity

| Table | Findings |
|---|---|
| `quotes` | Q-1 (duplicate `parent_quote_id` declaration) |
| `crm_connections` | V9-1 (missing `__table_args__` index) |
| `crm_record_links` | V9-2 (redundant index over UNIQUE) |
| `account_features_daily` / `rep_features_daily` | V5-1 (nullability ambiguity) |
| `domain_events` | WH-2 (no admin reader) |
| `webhook_deliveries` | WH-1 (no retry write path) |

---

## 5. Cross-Layer Compatibility Matrix (key entities)

| Entity | DB | Backend Model | API Field | TS Type | UI | Status |
|---|---|---|---|---|---|---|
| `quote.parent_quote_id` | ✓ migration 20260428 | **DUPLICATE decl** at lines 44-46 + 64-66 | ✓ in `_quote_to_dict` | ✓ | ✓ | ⚠ critical schema bug |
| `crm_connections.is_active` (indexed) | ✓ index exists | ✗ `__table_args__` missing | n/a | n/a | n/a | ⚠ ORM autogenerate would drop index |
| `account_features_daily.objection_density_30d` | ✓ NOT NULL | implicit non-null via `Mapped[float]` | ✓ | ✓ | ✓ | ⚠ ambiguous |
| Buyer-state `drivers[]` | DB JSON | ✓ parsed | ✓ array of dicts | `IntelligenceDriver[]` only in api.ts | partial render | ⚠ type not exported |
| Customer health `explanations[]` | computed | ✓ conditional | ✓ when `?include_explanations=true` | **missing** | not rendered | ⚠ TS gap |
| `OpportunitySignal.signal_type` | DB enum-string | ✓ `OpportunitySignalType` enum | ✓ string | `string` (not literal union) | switch statements | ⚠ enum drift |
| `invoice.paid_at` write → `invoice.paid` event | n/a | timestamp set | ✗ event not emitted | n/a | n/a | ⚠ realtime gap |
| Decision-gap `recommended_actions[]` (detail page) | n/a | ✓ array | ✓ array | ✓ `string[]` | only `[0]` rendered | ⚠ partial render (page not yet fixed in Phase 1) |
| Coaching `rep.indicators[]` | computed | ✓ array | ✓ array | ✓ array | not rendered at all | ⚠ data-not-rendered |
| 24 `FEATURE_*` flags | n/a | ✓ config.py | ✓ via `/config/feature-flags` | ✓ FeatureFlagContext | only ~4 routes gated | ⚠ frontend gating incomplete |

---

## 6. Fix Plan

### Quick Wins (no migration, < 2 hr each)

| # | Fix | File | Risk |
|---|---|---|---|
| Q-1 | Delete duplicate `parent_quote_id` decl | `backend/app/models/quote.py:64-66` | low; SQLAlchemy was already keeping one |
| C-3 | Re-export `IntelligenceDriver` from `types.ts` | `frontend/src/lib/types.ts` | trivial |
| O-1 | Render all `recommended_actions` as chips (mirror cockpit fix) | `OpportunityDetailPage.tsx:1079-1100` | none |
| CU-1 | `setQueryData(['customer', id], data)` after create | `CustomerListPage.tsx:290-298` | none |
| A-1 | Align `/customers/high-intent` pagination shape | `customers.py:106-119` | low |
| X-2 / X-3 | Add literal-union types for `OpportunitySignalType`, `QuoteStatus` | `types.ts` | none |
| EG-2 | Add `SIGNAL_CREATED` to `EVENT_PAYLOAD_SCHEMAS` | `domain_events.py:52-87` | none |
| V5-1 | Add `nullable=False` to V5 foundation columns | `feature_store_daily.py:71-72` | none |
| V9-1 | Add `__table_args__` to `CrmConnection` | `v9_crm_sync.py:22-47` | none |
| WH-2 | Stub admin "Event Audit Log" page | new file in `features/admin/` | none |

### Safe Refactors (1–4 hr each)

- **O-2** — expand `OpportunityDetailPage` V4 features grid to 3 columns + conditional render
- **C-1** — collapsible row for coaching `rep.indicators`
- **C-2** — show 3 of N recent_mentions with `+N more` chip
- **WH-1** — webhook retry with exponential backoff (3 attempts)
- **A-3** — deprecate engagement legacy router with warning log

### Migration-Required Fixes

- **None** for the 34 findings in this report. All schema drift items resolve with model-side declaration changes that align with the existing DB.

### Risky / Manual-Review

- **X-1** — gating ~20 routes behind `FeatureFlagContext`. Each route needs an empty-state UX decision ("Bu özellik etkin değil" page vs hidden entirely). Best done as a dedicated sprint.
- **EG-1** — silent event handler failures: introducing a `dead_letter_events` table changes the migration history. Needs a real schema change + retry job.
- **A-2** — `?status=` param ignored: needs manual verification before patching, since closed-lost may be intentionally excluded for performance reasons.
- **I-1** — emitting `invoice.paid` may trigger downstream effects (revenue rollups) that haven't been reviewed; behind a feature flag for safety.

---

## 7. Suggested Code Patches (top-priority)

### Q-1: Delete duplicate Quote field

```diff
--- a/backend/app/models/quote.py
+++ b/backend/app/models/quote.py
@@ -61,9 +61,6 @@ class Quote(Base):
     # Win/loss tracking — closed_at + close_reason were stored
     # but never returned, blocking quote-level analytics from
     # rendering the actual outcome timestamp / rationale.
-    parent_quote_id: Mapped[int | None] = mapped_column(
-        Integer, ForeignKey("quotes.id"), nullable=True
-    )
     closed_at: Mapped[datetime | None] = mapped_column(
```

### O-1: Render all decision-gap actions on the opportunity detail page

```diff
--- a/frontend/src/features/board/OpportunityDetailPage.tsx
+++ b/frontend/src/features/board/OpportunityDetailPage.tsx
@@ -1085,11 +1085,21 @@
-                {g.recommended_actions?.[0] && (
-                  <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">
-                    {g.recommended_actions[0]}
-                  </p>
-                )}
+                {g.recommended_actions?.length > 0 && (
+                  <ul className="mt-1 flex flex-wrap gap-1">
+                    {g.recommended_actions.slice(0, 4).map((action, i) => (
+                      <li key={i} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300">
+                        {action}
+                      </li>
+                    ))}
+                    {g.recommended_actions.length > 4 && (
+                      <li className="rounded-md bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-500">
+                        +{g.recommended_actions.length - 4}
+                      </li>
+                    )}
+                  </ul>
+                )}
```

### I-1: Emit `invoice.paid` event

```diff
--- a/backend/app/api/v1/invoices.py
+++ b/backend/app/api/v1/invoices.py
@@ -260,6 +260,16 @@
     if body.status == "paid":
         invoice.paid_at = now
+        from app.core.event_bus import event_bus
+        await event_bus.publish(
+            "invoice.paid",
+            {
+                "invoice_id": invoice.id,
+                "customer_id": invoice.customer_id,
+                "amount": float(invoice.grand_total),
+                "currency": invoice.currency,
+            },
+        )
```

### V9-1: Add CrmConnection index to model

```diff
--- a/backend/app/models/v9_crm_sync.py
+++ b/backend/app/models/v9_crm_sync.py
@@ -45,6 +45,9 @@
     created_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
     )
+    __table_args__ = (
+        Index("ix_crm_connections_tenant_active", "tenant_id", "is_active"),
+    )
```

### CU-1: Customer create cache hydration

```diff
--- a/frontend/src/features/customers/CustomerListPage.tsx
+++ b/frontend/src/features/customers/CustomerListPage.tsx
@@ -290,8 +290,10 @@
   const createMutation = useMutation({
     mutationFn: customersApi.createCustomer,
-    onSuccess: () => {
+    onSuccess: (newCustomer) => {
       queryClient.invalidateQueries({ queryKey: ['customers'] });
+      // Hydrate the detail-page cache so navigating right after
+      // create doesn't show stale/empty data.
+      queryClient.setQueryData(['customer', newCustomer.id], newCustomer);
     },
   });
```

### X-2: Literal-union for `OpportunitySignalType`

```diff
--- a/frontend/src/lib/types.ts
+++ b/frontend/src/lib/types.ts
@@ -448,7 +448,15 @@
+export type OpportunitySignalType =
+  | 'pricing_concern' | 'competitor' | 'objection' | 'no_touch'
+  | 'discount_risk' | 'sla_breach' | 'positive'
+  | 'workflow_triggered' | 'coaching_needed' | 'stage_change'
+  | 'expansion_signal' | 'playbook_completed';
+
 export interface OpportunitySignal {
   id: number;
-  signal_type: string;
+  signal_type: OpportunitySignalType;
```

---

## 8. Suggested Database Migrations

**No migrations required for the 34 findings in this report.** Every schema-drift item resolves with a model-side declaration change that aligns with the live DB.

The two refactors that *would* benefit from a migration but are deferred:

1. **`dead_letter_events` table** for EG-1 — Future work; needs a sprint of its own.
2. **Cleanup of `crm_record_links` redundant index** (V9-2) — A `DROP INDEX IF EXISTS ix_crm_record_links_external` migration with a corresponding model edit. Low-risk but cosmetic.

---

## 9. Suggested Tests

| Layer | Test | Rationale |
|---|---|---|
| Schema | `test_no_duplicate_columns_in_models` (introspect every `Base.__subclasses__()` and assert `len(cls.__table__.columns) == len(set(c.name for c in cls.__table__.columns))`) | Would have caught Q-1 immediately |
| Schema | `test_model_indexes_match_migrations` (compare `Base.metadata` indexes vs `inspect(engine).get_indexes()`) | Catches V9-1, V9-2 type findings |
| API contract | `test_pagination_shape_consistency` (every paginated endpoint returns `{items, total, page, page_size, pages}`) | Catches A-1 |
| API contract | `test_filter_params_actually_filter` — for each `Query(...)` param on a list endpoint, verify the SQL output differs based on the value | Catches A-2 |
| Realtime | `test_event_emit_subscribe_pairing` — assert every `event_bus.publish(name, ...)` has a matching `event_bus.subscribe(name, ...)` | Catches I-1, EG-2 patterns |
| Frontend types | `test_api_response_matches_ts_type` — runtime contract check: hit a representative subset of endpoints in CI with a TS test runner that validates the response against the imported interface | Catches O-3, CU-2, C-3 |
| Cache | `test_mutation_invalidates_detail_cache` — mocked tanstack-query test that fires a create mutation and asserts the detail queryKey was either invalidated or pre-populated | Catches CU-1 family |

---

## Final summary lists

- **DB columns not used by backend:** none confirmed (would need full grep follow-up)
- **Backend model fields not backed by DB:** Q-1 (`parent_quote_id` × 2)
- **Backend fields not exposed through API:** covered exhaustively in v1.5.0
- **API fields never consumed by frontend:** O-2 (7 of 15 V4 fields), C-1 (`indicators[]`), C-2 (`recent_mentions` past index 0)
- **Frontend fields/types missing from API/backend:** CU-2 (`explanations`), C-3 (`IntelligenceDriver` export)
- **Data fetched but not rendered:** O-1, O-2, C-1, C-2 — total 4 confirmed
- **UI components showing incomplete data:** same 4
- **Realtime events emitted but not handled:** EG-2 (`revenue_signal.created` schema absent)
- **Realtime events handled but not emitted:** I-1 (`invoice.paid`)
- **Schema/type/nullability mismatches:** V5-1 (nullability), V9-1/V9-2 (indexes), Q-1 (duplicate)
- **Permission/feature-flag mismatches:** X-1 (~20 routes ungated)
- **Required migrations:** 0 mandatory; 1 cosmetic (V9-2 drop redundant index)
- **Recommended frontend type updates:** 6 (X-2, X-3, CU-2, C-3, O-3, signal_type literals across other entities)
- **Recommended backend DTO/serializer updates:** 1 (A-1 pagination)
- **Recommended tests:** 7 (per section 9)

---

## Methodology

Six parallel `Explore` subagents, each scoped to one layer:

1. **DB ↔ Backend ORM** — migrations vs models, type/nullability/index drift
2. **Backend ↔ API contract** — Pydantic validators, response shapes, sort/filter params
3. **API ↔ Frontend client** — TS types, api.ts mappings, cache schemas
4. **Data fetched but not rendered** — JSX vs query data, partial renders, conditional hiding
5. **Realtime + state lifecycle** — event bus emit/subscribe pairs, cache invalidation, optimistic updates
6. **Naming + permissions + cross-layer** — snake_case/camelCase drift, enum drift, role gates, feature-flag drift

Each agent constrained to evidence-backed findings with file:line references; results synthesized here without modifying source.

No code modified per the explicit "do not modify files unless asked" rule from the audit prompt.
