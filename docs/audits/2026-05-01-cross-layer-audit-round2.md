# Cross-Layer Audit Report — Honeywell Sales Suite (Round 2, post-v1.6.0)

**Date:** 2026-05-01
**Branch:** `deploy/render-sandbox`
**HEAD:** `85710a9` (post v1.6.0 — 18 fixes from round-1 audit shipped)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions · State/lifecycle

Synthesized from 6 parallel layer-focused scans. Findings exclude items already resolved in v1.5.0–v1.6.0. Each finding is annotated with confidence; "needs manual verification" flags are honest and should not be acted on without re-reading the source.

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| Total new findings | **48** |
| Critical | 3 |
| High | 11 |
| Medium | 22 |
| Low | 12 |

**Most-affected surfaces:**
- **Multi-tenant isolation** (3 critical) — bulk endpoints + approval/quote endpoints missing `assert_same_tenant`
- **Detail pages dropping fetched fields** (12 findings, "data-not-rendered") — biggest UX impact
- **Domain-event publishers vs subscribers** (4 findings, realtime mismatch)
- **Pagination envelope inconsistency** (3 list endpoints still on `skip/limit`)

**Headline issues that warrant immediate review:**
1. **TEN-1** Cross-tenant write via `POST /opportunities/bulk-action` — verified
2. **TEN-2** Cross-tenant read via `GET /approvals/history`  — verified
3. **TEN-3** Cross-tenant manager exploit via `GET /quotes/{id}/compare/{other_id}` — verified, manager-only
4. **EVT-1/EVT-2** `lead.score_changed` and `opportunity.score_changed` defined but never emitted (dead realtime code path)

**Categories with the most code touched per fix:**
- Multi-tenant guards: ~15-line tactical patch each, no migration
- Pagination envelope alignment: ~5 lines per endpoint
- Data-not-rendered fixes: pure JSX additions, zero schema work

---

## 2. Findings by Feature / Page

### 2.1 Multi-tenant security (CRITICAL × 3)

#### TEN-1 — `POST /opportunities/bulk-action` performs writes across tenants
- **Severity:** **critical**
- **Category:** permission / cross-tenant write
- **Evidence:** [backend/app/api/v1/opportunities.py:665-747](../../backend/app/api/v1/opportunities.py#L665-L747); fetch query at line 683-684 is `select(Opportunity).where(Opportunity.id.in_(ids))` with **no tenant scoping**
- **Impact:** A manager (or rep, for non-delete actions) can pass arbitrary opportunity IDs from any tenant and mutate them — change_stage, assign, mark_won/lost, export. The 404 error path doesn't help: the user only needs to guess valid IDs.
- **Root cause:** The endpoint pre-dates V8 multi-tenancy and was never retrofitted with `assert_same_tenant`.
- **Minimal fix:**
  ```python
  result = await db.execute(
      select(Opportunity).where(
          Opportunity.id.in_(ids),
          Opportunity.tenant_id == current_user.tenant_id,  # ← add
      )
  )
  ```
- **Long-term fix:** Add a reusable `tenant_scoped_query(model, current_user)` helper and use it across every bulk endpoint; add an integration test that creates two tenants and asserts cross-tenant access returns 404.
- **Tests:** new `tests/test_bulk_action_tenant_isolation.py`

#### TEN-2 — `GET /approvals/history` leaks any entity's approval history across tenants
- **Severity:** **critical**
- **Category:** permission / cross-tenant read
- **Evidence:** [backend/app/api/v1/approvals.py:187-198](../../backend/app/api/v1/approvals.py#L187-L198); `entity_type` + `entity_id` are accepted as query params and the service is called with no tenant filter or entity ownership check
- **Impact:** Any authenticated user can enumerate approval history for `entity_type=opportunity` or `=quote` from any tenant by guessing IDs. Data exposed: who approved, when, comments, escalation chain.
- **Minimal fix:**
  ```python
  # Validate the entity belongs to the caller's tenant first
  await assert_entity_in_tenant(db, entity_type, entity_id, current_user)
  history = await service.get_approval_history(entity_type, entity_id)
  ```
  Implement `assert_entity_in_tenant` to dispatch to the correct model (Opportunity, Quote, etc.) and call the existing `assert_same_tenant`.
- **Tests:** add `test_approval_history_rejects_other_tenant`

#### TEN-3 — `GET /quotes/{id}/compare/{other_id}` allows a manager to compare quotes from different tenants
- **Severity:** **high** (downgraded from agent's "critical" — exploit requires SALES_MANAGER role)
- **Category:** permission / cross-tenant read
- **Evidence:** [backend/app/api/v1/quotes.py:610-678](../../backend/app/api/v1/quotes.py#L610-L678); auth check at line 628-631 verifies role+ownership but never tenant
- **Impact:** A manager from Tenant A who learns a Tenant B quote ID can view its line items, prices, and discounts.
- **Minimal fix:** add `assert_same_tenant(quote_a, current_user)` and `assert_same_tenant(quote_b, current_user)` after lines 619/624.
- **Tests:** `test_quote_compare_rejects_cross_tenant`

### 2.2 Realtime / Event bus (HIGH × 2, MEDIUM × 4)

#### EVT-1 — `DomainEvents.LEAD_SCORE_CHANGED` defined but never published
- **Severity:** high
- **Category:** realtime mismatch
- **Evidence:** [backend/app/services/domain_events.py:36](../../backend/app/services/domain_events.py#L36) defines the constant + payload schema; grep finds no `event_bus.publish("lead.score_changed", ...)` site. The lead detail page subscribes (`LeadDetailPage.tsx`) and gets nothing.
- **Impact:** Score-history feed on lead detail is silent because nothing is ever emitted; the on-read recompute (`leads.py:451-464`) writes to the DB but doesn't publish.
- **Minimal fix:** in the lead-scoring service, after persisting the new score, call:
  ```python
  await emit_domain_event(db, DomainEvents.LEAD_SCORE_CHANGED, {
      "lead_id": lead.id, "old_score": old, "new_score": new, "reason": reason,
  })
  ```

#### EVT-2 — `DomainEvents.OPP_SCORE_CHANGED` defined but never published
- **Severity:** high
- **Same shape as EVT-1.** [backend/app/services/domain_events.py:37](../../backend/app/services/domain_events.py#L37). Add `OPP_SCORE_CHANGED` to `EVENT_PAYLOAD_SCHEMAS` (currently absent) and emit from the deal-health pipeline.

#### EVT-3 — `event_bus.publish()` swallows handler exceptions silently with no Sentry capture
- **Severity:** medium
- **Evidence:** [backend/app/core/event_bus.py:36-68](../../backend/app/core/event_bus.py#L36-L68) — handler failures are `logger.warning`d but never sent to Sentry.
- **Impact:** A workflow rule that crashes for one event is invisible until someone reads logs.
- **Minimal fix:**
  ```python
  except Exception as exc:
      logger.warning("Event handler %s failed for %s: %s", handler.__name__, event_type, exc)
      sentry_sdk.capture_exception(exc)  # ← add
  ```

#### EVT-4 — `_on_workflow_event()` doesn't validate payload shape
- **Severity:** medium
- **Evidence:** [backend/app/main.py:280-300](../../backend/app/main.py#L280-L300) maps event types to entity-resolver tuples but doesn't gate on required fields. If a publisher omits `quote_id` for `quote.approved`, the workflow silently no-ops.
- **Minimal fix:** add explicit `if not payload.get("quote_id"): logger.warning(...); return` per branch.

#### EVT-5 — `_on_revenue_signal_created` accesses `payload['signal_id']` without guard
- **Severity:** medium
- **Evidence:** [backend/app/main.py:256](../../backend/app/main.py#L256). EG-2 (round-1) added the schema, but the runtime handler still assumes the key.
- **Minimal fix:** `signal_id = payload.get("signal_id"); if signal_id is None: return`.

#### EVT-6 — Webhook deliveries have no dead-letter persistence
- **Severity:** medium
- **Evidence:** WH-1 (round-1) added 3-attempt retry + `retry_count`; if all 3 still fail there's no replay queue.
- **Minimal fix (deferred):** `dead_letter_webhook_deliveries` table + admin "replay" button. Out of scope for a hotfix sprint.

### 2.3 Customer pages (HIGH × 3, MEDIUM × 1)

#### F-1 — Customer create/edit forms can't set `website`/`linkedin_url`
- **Severity:** high
- **Category:** data-not-rendered (write side)
- **Evidence:** [CustomerDetailPage.tsx:80-88, 437-479](../../frontend/src/features/customers/CustomerDetailPage.tsx#L80-L88) and [CustomerListPage.tsx:259-267, 506-540](../../frontend/src/features/customers/CustomerListPage.tsx#L259-L267); backend `customers.update` accepts both fields, the read view renders them, but the form schema doesn't.
- **Impact:** Reps can see auto-enriched values but cannot correct bad enrichment manually.
- **Fix:** add `website` + `linkedin_url` to `INITIAL_FORM` and add two `<Input>` rows in the modal.

#### F-2 — `CustomerCard` list omits all enrichment metadata
- **Severity:** high
- **Evidence:** [CustomerListPage.tsx:86-256](../../frontend/src/features/customers/CustomerListPage.tsx#L86-L256). `industry`, `employee_count`, `annual_revenue`, `enriched_at` returned per row, never displayed.
- **Fix:** small badge row after line 127 — `{c.industry && <Badge>{c.industry}</Badge>}` plus a sparkles icon when `enriched_at` is set.

#### F-3 — `AtRiskCustomersCard` drops `recommendations[]` (the entire point of the widget)
- **Severity:** high
- **Evidence:** [AtRiskCustomersCard.tsx:67-108](../../frontend/src/features/dashboard/AtRiskCustomersCard.tsx#L67-L108). API returns full `CustomerHealthReport` with `recommendations[]`, only score/risk_level rendered.
- **Fix:** add expand chevron rendering top 2 recommendations.

#### CU-3 — `Customer.tenant_id` returned by the model but stripped from the API response
- **Severity:** medium
- **Evidence:** [backend/app/api/v1/customers.py](../../backend/app/api/v1/customers.py) `_customer_to_dict()` (~lines 902-934) omits `tenant_id`; model has it.
- **Impact:** Frontend cannot display tenant scope; multi-tenant analytics blind.
- **Fix:** add `"tenant_id": customer.tenant_id` to the dict; mirror in `Customer` TS type.

### 2.4 Lead detail (HIGH × 1)

#### F-5 — `LeadDetailPage` ignores `score_breakdown` even though backend computes it specifically for this view
- **Severity:** high
- **Evidence:** [backend/app/api/v1/leads.py:451-464](../../backend/app/api/v1/leads.py#L451-L464) explicitly attaches `score_breakdown` only on the detail endpoint; [LeadDetailPage.tsx:143-348](../../frontend/src/features/leads/LeadDetailPage.tsx#L143-L348) never reads it.
- **Impact:** The "why is this lead 67/100" answer is fetched and discarded.
- **Fix:** under the `<ScoreRing>`, render `lead.score_breakdown.factors.map(...)`.

### 2.5 Cockpit (HIGH × 1)

#### F-4 — `KpiStrip` drops `signal_stats.critical_count`, `high_count`, breakdowns
- **Severity:** high
- **Evidence:** [CockpitPage.tsx:72-148](../../frontend/src/features/cockpit/CockpitPage.tsx#L72-L148). Only `signal_stats.total` shown; `critical_count` (the headline manager number) discarded.
- **Fix:** add `<span className="text-xs text-red-600">crit {data.signal_stats.critical_count} · high {data.signal_stats.high_count}</span>` under the signals tile.

### 2.6 Subscriptions (MEDIUM × 2)

#### F-7 — `MrrDashboard.top_customers` not rendered
- **Severity:** medium
- **Evidence:** [SubscriptionListPage.tsx:79-82, 144-181](../../frontend/src/features/subscriptions/SubscriptionListPage.tsx#L79-L82). Backend returns `top_customers: [{customer_id, name, mrr}]`; KPI tiles + a renewal badge are the only UI.
- **Fix:** add a "Top customers by MRR" card below the KPI grid.

#### F-8 — `SubscriptionDetailPage` hides `customer_id`, `quote_id`, `created_by`, `updated_at`
- **Severity:** medium
- **Evidence:** [SubscriptionDetailPage.tsx:154-219](../../frontend/src/features/subscriptions/SubscriptionDetailPage.tsx#L154-L219).
- **Impact:** Rep has no link from a subscription back to its quote/customer.
- **Fix:** add two grid cells linking to `/customers/{id}` and `/quotes/{id}`.

### 2.7 Coaching / Insights / Activity (MEDIUM × 3)

- **F-9** [`CoachingRepPage` indicator rows](../../frontend/src/features/coaching/CoachingRepPage.tsx#L365-L393) drop `description` + `raw_value` — rep sees a number with no context.
- **F-10** [`InsightsPage` conversation search](../../frontend/src/features/insights/InsightsPage.tsx#L391-L415) drops `occurred_at`, `owner_id`, total result count.
- **F-11** [`ActivityLogPanel`](../../frontend/src/features/board/ActivityLogPanel.tsx#L94-L126) never displays `agenda` or `attendees_json` — meeting agenda is captured then never read.

### 2.8 Buyer relationship map (MEDIUM × 1)

#### F-12 — `StakeholderCard` hides `email`, `phone`, `notes`, `is_auto_detected`
- **Severity:** medium
- **Evidence:** [BuyerRelationshipMap.tsx:185-225](../../frontend/src/features/opportunities/BuyerRelationshipMap.tsx#L185-L225). Form even *collects* `email` but the card never shows it.
- **Fix:** add `<a href="mailto:{s.email}">` row + an "AI" badge when `is_auto_detected`.

### 2.9 Opportunity detail (MEDIUM × 1)

#### F-6 — Buyer-state timeline drops `drivers[]`
- **Severity:** medium
- **Evidence:** [OpportunityDetailPage.tsx:1104-1131](../../frontend/src/features/board/OpportunityDetailPage.tsx#L1104-L1131). Each snapshot has `drivers: unknown[]` (the *reason* for the classification); rendered fields are state + confidence only.
- **Fix:** at line 1119 append `(it.drivers as string[]).slice(0,3).join(', ')` chip row.

### 2.10 Backend ↔ API contract (HIGH × 2, MEDIUM × 4)

#### Q-2 — `Quote.tenant_id` not serialized
- **Severity:** high (sibling of CU-3)
- **Evidence:** [backend/app/api/v1/quotes.py](../../backend/app/api/v1/quotes.py) `_quote_to_dict()` (~line 683-750).
- **Fix:** add `"tenant_id": quote.tenant_id`.

#### A-4 — `GET /invoices/` returns `{items, total, skip, limit}` (legacy envelope)
- **Severity:** medium
- **Evidence:** [backend/app/api/v1/invoices.py:123-153](../../backend/app/api/v1/invoices.py#L123-L153). Round-1 standardized customers; this endpoint slipped.
- **Fix:** convert to page/page_size + emit `pages`.

#### A-5 — `GET /campaigns/` same issue
- **Severity:** medium
- **Evidence:** [backend/app/api/v1/campaigns.py:102-137](../../backend/app/api/v1/campaigns.py#L102-L137). `{items, total, skip, limit}`.
- **Fix:** same as A-4.

#### A-6 — `GET /contracts/` returns `{"contracts": [...]}` (no pagination at all)
- **Severity:** high
- **Evidence:** [backend/app/api/v1/contracts.py:80-98](../../backend/app/api/v1/contracts.py#L80-L98). Inconsistent root key + unbounded list.
- **Fix:** rename root key to `items`, add pagination params, add `total`/`pages`.

#### A-7 — `Invoice.status` exposed as raw string with no Enum class
- **Severity:** low
- **Evidence:** [backend/app/api/v1/invoices.py:94](../../backend/app/api/v1/invoices.py#L94). Other status fields use `enums.QuoteStatus` etc.; Invoice has none.
- **Fix:** add `class InvoiceStatus(str, Enum)` to `models/enums.py` (`draft|sent|paid|overdue|voided`); use it in transition validator.

#### A-8 — `POST /invoices/from-quote` returns `{message, id, invoice_number}` only; sibling GET returns 16 fields
- **Severity:** medium
- **Evidence:** [backend/app/api/v1/invoices.py:185-189](../../backend/app/api/v1/invoices.py#L185-L189).
- **Fix:** return full `_invoice_to_dict(invoice)` so the client can render immediately without a follow-up GET.

#### A-9 — `invoice.paid` event payload missing `quote_id`/`contract_id`
- **Severity:** medium
- **Evidence:** Round-1 I-1 introduced the publish at [backend/app/api/v1/invoices.py:277-291](../../backend/app/api/v1/invoices.py#L277-L291) with `{invoice_id, customer_id, amount, currency}`; downstream revenue-recognition needs the quote/contract link to update ARR.
- **Fix:** add `"quote_id": invoice.quote_id, "contract_id": invoice.contract_id` (verify column names).

### 2.11 Database ↔ ORM drift (HIGH × 1, MEDIUM × 4)

> Note: the agent that ran this scan had partial file-access issues; treat the items below as starting points, **not** confirmed drift. Each requires `python -c "from app.models.X import Y; print(...)"` style verification before patching.

#### DB-1 — `DomainEvent.created_at` declared `nullable=True` despite default
- **Severity:** high *(needs verification)*
- **Evidence:** [backend/app/models/sequence_v2.py:75-77](../../backend/app/models/sequence_v2.py#L75-L77) per agent. Pattern is unusual: `Mapped[datetime | None]` with a `default=` lambda.
- **Risk:** Audit-log rows can theoretically have null timestamps if the default ever fails to apply.
- **Fix:** if intent is "always present", change to `Mapped[datetime]` + `nullable=False` (model-only).

#### DB-2 — `Contact.seniority_score` (V5 foundation) lacks explicit `nullable=False`
- **Severity:** medium
- **Evidence:** model declares `Mapped[int] = mapped_column(Integer, default=50)`; migration declares `INTEGER NOT NULL DEFAULT 50`.
- **Fix:** mirror the V5-1 pattern from round-1 — add `nullable=False`.

#### DB-3 — `OpportunityFeaturesDaily.decision_maker_count` (V6) same pattern
- **Severity:** medium
- **Evidence:** [feature_store_daily.py:46](../../backend/app/models/feature_store_daily.py#L46) vs migration line 31. Same model-side `nullable=False` fix.

#### DB-4 — `OpportunitySignal` uses `backref` instead of `back_populates`
- **Severity:** low
- **Evidence:** model uses `backref="signals"` per agent; `Opportunity` has no explicit `signals = relationship(...)` declaration.
- **Fix:** convert to `back_populates` for type-checker friendliness; no runtime behavior change.

#### DB-5 — `CustomFieldValue.value_date` stored as `DateTime(timezone=True)` instead of `Date`
- **Severity:** medium
- **Evidence:** [custom_field.py:64-66](../../backend/app/models/custom_field.py#L64-L66) per agent.
- **Risk:** Semantic drift; "date" inputs get interpreted in UTC and may show off-by-one in non-UTC time zones.
- **Fix:** **migration required** — `ALTER COLUMN value_date TYPE DATE USING value_date::date`. Verify no callers rely on the time component first.

### 2.12 Frontend types (MEDIUM × 5)

> The API↔Frontend agent produced findings of mixed quality. The items below are the ones I judge worth pursuing; the `won_reason`, `payment_terms`, and "dual probability scale" claims **need source verification** — they may not exist in the live API.

#### TS-1 — `OpportunityFeaturesDailyLatest.momentum_score` may be `NaN`
- **Severity:** medium *(needs verification)*
- **Evidence:** Agent's claim that backend aggregations can return JS `NaN`. If true, `score.toFixed(0)` crashes.
- **Fix:** add `Number.isFinite()` guard at render sites OR coerce `NaN` → `null` in `_features_to_dict`.

#### TS-2 — `notificationsApi.getNotifications` uses `<T = unknown>` generic with `as any`-style cast
- **Severity:** medium
- **Evidence:** [api.ts:811-816](../../frontend/src/lib/api.ts#L811-L816) per agent.
- **Fix:** drop the generic; type as `Notification[]` and let callers handle the concrete shape.

#### TS-3 — `featureStoreApi.getLatest` does `data?.data ?? null`, so any future flat response silently returns null
- **Severity:** low
- **Evidence:** [api.ts:926-927](../../frontend/src/lib/api.ts#L926-L927).
- **Fix:** pin the response with a Pydantic `BaseModel` on the backend and remove the defensive fallback.

#### TS-4 — Frontend `Customer.territory_id` typed but `territory` object never returned (or always sparse)
- **Severity:** low
- **Evidence:** types.ts has `territory_id?: number | null`; no nested `territory` object; UI has no way to show the territory name without a second fetch.
- **Fix:** backend should embed `territory: {id, name}` on customer responses, OR frontend builds a `territories` lookup and joins client-side.

#### TS-5 — `CockpitKpis.signal_stats` typed as full breakdown but only `total` consumed (mirrors F-4)
- **Severity:** low
- **Evidence:** see F-4. The TS type already has the field, the JSX just discards it.

### 2.13 Cross-cutting (MEDIUM × 3, LOW × 4)

#### X-5 — Sentry events lack a `release` tag
- **Severity:** medium
- **Evidence:** `dependencies.get_current_user` sets user/role tags but not release. Frontend exposes the release via `/config/feature-flags` but backend errors aren't tagged the same way.
- **Fix:** at process start (e.g. `sentry_sdk.init(release=os.environ.get("SENTRY_RELEASE", "dev"), ...)`).

#### X-6 — Frontend Sidebar references 4 feature flags not in `_PUBLIC_FEATURE_FLAGS`
- **Severity:** medium
- **Evidence:** [Sidebar.tsx:52](../../frontend/src/components/layout/Sidebar.tsx#L52) per agent: `FEATURE_INSIGHTS`, `FEATURE_COCKPIT`, `FEATURE_COMPLIANCE`, `FEATURE_KVKK` — backend `/config/feature-flags` allow-list at [config.py:32-56](../../backend/app/api/v1/config.py#L32-L56) doesn't include them.
- **Impact:** They silently always evaluate to `false` when read by `useFeatureFlag(...)`.
- **Fix:** add to the allow-list OR change the Sidebar to gate by role only, depending on intent.

#### X-7 — Inconsistent `require_role(...)` syntax across the codebase
- **Severity:** low
- **Evidence:** some endpoints use single-role, others multi-role with `,`-separated args. No actual bypass — this is hygiene.
- **Fix:** lint rule or codemod to canonicalize.

#### A-3 (residual) — engagement legacy router still mounted
- **Severity:** low
- **Status:** Round-1 marked `deprecated=True` and added per-request log. Sunset date in code is **2026-09**; still serves traffic. No new fix needed — listed for tracking.

#### Honorable mentions (low) — surfaced during the data-not-rendered sweep
- `frontend/src/features/dashboard/DashboardPage.tsx:207` — `pending_value` destructured but never used.
- `frontend/src/features/customers/HighIntentAccountsPage.tsx:44-106` — `data.total` not displayed in card title.
- `frontend/src/features/customers/CustomerDetailPage.tsx:780-792` — `account360.risk_summary.unresolved_high_signals`, `risk_level`, `health_score` discarded.
- `frontend/src/features/parts-intel/PartsIntelligenceDashboardPage.tsx:13-20` — `SummaryPayload.generated_at` and `heatmap_months_covered` fetched, never rendered.

---

## 3. Findings by API Endpoint

| Endpoint | Findings |
|---|---|
| `POST /opportunities/bulk-action` | TEN-1 (cross-tenant) |
| `GET /approvals/history` | TEN-2 (cross-tenant) |
| `POST /approvals/delegate` | (related; needs verification of `ApprovalRule.tenant_id`) |
| `GET /quotes/{id}/compare/{other_id}` | TEN-3 (manager cross-tenant) |
| `GET /quotes/`, `GET /quotes/{id}` | Q-2 (tenant_id stripped) |
| `GET /customers/`, `GET /customers/{id}` | CU-3 (tenant_id stripped), F-1, F-2 |
| `GET /invoices/` | A-4 (legacy pagination) |
| `POST /invoices/from-quote` | A-8 (truncated response) |
| `PATCH /invoices/{id}/status` | A-7 (string status), A-9 (event payload) |
| `GET /campaigns/` | A-5 (legacy pagination) |
| `GET /contracts/` | A-6 (no pagination, root key) |
| `GET /v4/opportunities/{id}/features/latest` | TS-1, TS-3 |
| `GET /buyer-state/.../timeline` | F-6 |
| `GET /coaching/.../scorecards` | F-9 |
| `GET /cockpit/kpis` | F-4 (signal_stats breakdown) |
| `GET /customer-health/at-risk` | F-3 |
| `GET /leads/{id}` | F-5 (score_breakdown) |
| `GET /subscriptions/mrr-dashboard` | F-7 |
| `GET /subscriptions/{id}` | F-8 |
| `GET /opportunities/{id}/activities` | F-11 |
| `GET /opportunities/{id}/stakeholders` | F-12 |
| `event_bus.publish("lead.score_changed")` | EVT-1 (never emitted) |
| `event_bus.publish("opportunity.score_changed")` | EVT-2 (never emitted) |

---

## 4. Findings by DB Entity / Table

| Table | Findings |
|---|---|
| `opportunities` | TEN-1 |
| `quotes` | TEN-3, Q-2 |
| `customers` | CU-3 |
| `domain_events` | DB-1 (nullability ambiguity) |
| `contacts` (V5) | DB-2 |
| `opportunity_features_daily` | DB-3 |
| `opportunity_signals` | DB-4 (backref vs back_populates) |
| `custom_field_values` | DB-5 (DateTime → Date) |
| `approval_requests` | TEN-2 |

---

## 5. Cross-Layer Compatibility Matrix (key entities)

| Entity | DB | Backend Model | API Field | TS Type | UI | Status |
|---|---|---|---|---|---|---|
| `customer.tenant_id` | ✓ | ✓ | ✗ stripped | n/a | n/a | ⚠ leak in dict |
| `quote.tenant_id` | ✓ | ✓ | ✗ stripped | n/a | n/a | ⚠ leak in dict |
| `customer.industry/website/linkedin_url/enriched_at` | ✓ | ✓ | ✓ | ✓ | partial (read only, not in form/list) | ⚠ data-not-rendered |
| `lead.score_breakdown` | computed | ✓ | ✓ (detail only) | ✓ | not rendered | ⚠ data-not-rendered |
| `cockpit.signal_stats.{critical,high}_count` | computed | ✓ | ✓ | ✓ | only `.total` rendered | ⚠ data-not-rendered |
| `customer_health.recommendations[]` | computed | ✓ | ✓ | ✓ | dropped on at-risk card | ⚠ data-not-rendered |
| `subscription.{customer_id,quote_id}` | ✓ | ✓ | ✓ | ✓ | not surfaced in detail | ⚠ data-not-rendered |
| `mrr_dashboard.top_customers` | computed | ✓ | ✓ | ✓ | dropped | ⚠ data-not-rendered |
| `stakeholder.{email,phone,is_auto_detected}` | ✓ | ✓ | ✓ | ✓ | dropped on card | ⚠ data-not-rendered |
| `activity.{agenda,attendees_json}` | ✓ | ✓ | ✓ | ✓ | dropped on log | ⚠ data-not-rendered |
| `buyer_state.drivers[]` | ✓ | ✓ | ✓ | `unknown[]` | dropped | ⚠ type-loose + data-not-rendered |
| `lead.score_changed` event | n/a | constant + schema | ✗ never emitted | subscriber wired | nothing arrives | ⚠ orphan event |
| `opportunity.score_changed` event | n/a | constant only | ✗ never emitted | n/a | n/a | ⚠ orphan event |
| `invoices` list pagination | n/a | n/a | `{items,total,skip,limit}` | expects `{...,page,page_size,pages}` | partial | ⚠ envelope drift |
| `contracts` list pagination | n/a | n/a | `{contracts: [...]}` (no pagination) | n/a | n/a | ⚠ envelope drift |
| `Opportunity` (bulk-action) | tenant_id ✓ | tenant_id ✓ | not enforced on this endpoint | n/a | n/a | ⛔ cross-tenant |
| `ApprovalRequest` (history) | n/a | tenant scoping unclear | not enforced | n/a | n/a | ⛔ cross-tenant |

---

## 6. Fix Plan

### Quick wins (no migration, < 2 hr each)

| # | Fix | File | Risk |
|---|---|---|---|
| Q-2 | Add `tenant_id` to `_quote_to_dict` | `quotes.py` | low |
| CU-3 | Add `tenant_id` to `_customer_to_dict` | `customers.py` | low |
| F-3 | Render `recommendations[]` on AtRiskCustomersCard | dashboard | none |
| F-4 | Render `signal_stats.critical/high_count` | cockpit | none |
| F-5 | Render `score_breakdown.factors` on LeadDetailPage | leads | none |
| F-6 | Render `drivers[]` on buyer-state timeline | OpportunityDetailPage | none |
| F-7 | Render `top_customers` on MrrDashboard | subscriptions | none |
| F-8 | Add customer/quote links on SubscriptionDetailPage | subscriptions | none |
| F-9 | Add `description` + `raw_value` under coaching indicators | coaching | none |
| F-10 | Add `occurred_at` + `total` count to InsightsPage | insights | none |
| F-11 | Render `agenda` + `attendees_json` on ActivityLogPanel | board | none |
| F-12 | Render `email`/`phone`/AI badge on StakeholderCard | opportunities | none |
| EVT-3 | Add `sentry_sdk.capture_exception` in event_bus.publish | event_bus | none |
| EVT-4 | Validate workflow event payloads | main.py | none |
| EVT-5 | Guard `signal_id` access in revenue-signal handler | main.py | none |
| X-5 | Add `release` tag to `sentry_sdk.init` | dependencies/main | none |
| X-6 | Add 4 missing flags to `_PUBLIC_FEATURE_FLAGS` | config.py | none |
| DB-2/DB-3 | Add `nullable=False` to V5/V6 model columns | feature_store_daily, v5_foundation | none |
| DB-4 | `back_populates` on OpportunitySignal | opportunity model | none |

### Safe refactors (1–4 hr each)

- **F-1, F-2** — extend customer create/edit form + list card with enrichment fields
- **A-4, A-5** — convert invoice + campaign list endpoints to canonical pagination envelope (frontend list components likely already tolerate it; verify before merge)
- **A-6** — `/contracts/` end-to-end refactor: rename root key, add pagination, search input
- **A-7** — formalize `InvoiceStatus(str, Enum)` and migrate the transition validator
- **A-8** — return full invoice dict from `POST /invoices/from-quote`
- **A-9** — extend `invoice.paid` payload with `quote_id`/`contract_id`
- **EVT-1, EVT-2** — wire missing emitters for lead/opportunity score changes
- **TS-2** — drop `<T = unknown>` from `getNotifications`

### Migration-required fixes

- **DB-5** — `ALTER COLUMN value_date TYPE DATE` on `custom_field_values`. Backfill is trivial (cast). Migration file: `20260502_custom_field_value_date_to_date.py`. Verify no calling code depends on the time component first.
- **DB-1** — if `DomainEvent.created_at` is intended NOT NULL, add a migration that backfills any null rows to `now()` then sets NOT NULL. Risk: small; the column has a default so existing rows likely have values.
- *(optional, deferred)* Dead-letter table for webhook deliveries (EVT-6).

### Risky / manual review

- **TEN-1, TEN-2, TEN-3** — multi-tenant guards. Should land as a single PR with integration tests per endpoint to prove cross-tenant access is rejected. **Do not deploy without tests** — the bulk endpoint is a sales-rep-callable surface.
- **TS-1** — `momentum_score: NaN` claim is unverified. Reproduce locally first; if real, the right fix is backend-side (coerce to null in serializer), not frontend-side.
- **DB-1, DB-5** — schema changes; deserve their own deployment window.

---

## 7. Suggested Code Patches (top priority)

### TEN-1: Tenant-scope the bulk-action fetch

```diff
--- a/backend/app/api/v1/opportunities.py
+++ b/backend/app/api/v1/opportunities.py
@@ -682,7 +682,11 @@ async def bulk_action_opportunities(
     # Validate that all IDs exist
     result = await db.execute(
-        select(Opportunity).where(Opportunity.id.in_(ids))
+        select(Opportunity).where(
+            Opportunity.id.in_(ids),
+            # Tenant guard — added 2026-05-01 (audit TEN-1).
+            Opportunity.tenant_id == current_user.tenant_id,
+        )
     )
     opps = result.scalars().all()
```

### TEN-2: Validate entity ownership in approval history

```diff
--- a/backend/app/api/v1/approvals.py
+++ b/backend/app/api/v1/approvals.py
@@ -195,6 +195,10 @@ async def approval_history(
 ):
     """Get approval history for a specific entity."""
     service = ApprovalService(db)
+    # Tenant guard — added 2026-05-01 (audit TEN-2). Without this an
+    # authenticated user can enumerate any entity's approval chain by
+    # guessing IDs.
+    await service.assert_entity_in_tenant(entity_type, entity_id, current_user)
     history = await service.get_approval_history(entity_type, entity_id)
     return {"items": [_request_to_dict(r) for r in history]}
```

(Implement `assert_entity_in_tenant` to dispatch to the correct model and call `assert_same_tenant`.)

### TEN-3: Add tenant assertions to compare_quotes

```diff
--- a/backend/app/api/v1/quotes.py
+++ b/backend/app/api/v1/quotes.py
@@ -619,12 +619,14 @@ async def compare_quotes(
     quote_a = result_a.scalar_one_or_none()
     if not quote_a:
         raise NotFoundException(f"Teklif {quote_id} bulunamadi")
+    assert_same_tenant(quote_a, current_user, exception_cls=NotFoundException)

     result_b = await db.execute(select(Quote).where(Quote.id == other_id))
     quote_b = result_b.scalar_one_or_none()
     if not quote_b:
         raise NotFoundException(f"Teklif {other_id} bulunamadi")
+    assert_same_tenant(quote_b, current_user, exception_cls=NotFoundException)
```

### EVT-1: Emit lead.score_changed

```diff
--- a/backend/app/services/lead_scoring_service.py
+++ b/backend/app/services/lead_scoring_service.py
@@ ...
+    from app.services.domain_events import emit_domain_event, DomainEvents
+    await emit_domain_event(
+        db,
+        DomainEvents.LEAD_SCORE_CHANGED,
+        {
+            "lead_id": lead.id,
+            "old_score": old_score,
+            "new_score": new_score,
+            "reason": reason or "manual_recompute",
+        },
+    )
```
(Exact file path TBD; the change belongs at every site that updates `lead.score`.)

### F-5: Render score_breakdown on LeadDetailPage

```diff
--- a/frontend/src/features/leads/LeadDetailPage.tsx
+++ b/frontend/src/features/leads/LeadDetailPage.tsx
@@ ...  (under the <ScoreRing>)
+{lead.score_breakdown?.factors?.length ? (
+  <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
+    {lead.score_breakdown.factors.slice(0, 5).map((f) => (
+      <li key={f.name} className="flex justify-between">
+        <span>{f.label}</span>
+        <span className="tabular-nums text-slate-500">+{f.points}</span>
+      </li>
+    ))}
+  </ul>
+) : null}
```

### Q-2 + CU-3: Round-trip tenant_id

```diff
--- a/backend/app/api/v1/quotes.py
+++ b/backend/app/api/v1/quotes.py
@@ ...
     return {
         "id": quote.id,
+        "tenant_id": quote.tenant_id,
         "quote_number": quote.quote_number,
```

(Identical change in `_customer_to_dict`.)

---

## 8. Suggested Database Migrations

### `20260502_custom_field_value_date_to_date.py` (DB-5)

```python
"""custom_field_values.value_date: DateTime → Date"""
from alembic import op

revision = "20260502_custom_field_value_date_to_date"
down_revision = "20260428_v13_audit_tenant"

def upgrade() -> None:
    op.execute("""
        ALTER TABLE custom_field_values
        ALTER COLUMN value_date TYPE DATE
        USING value_date::date
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE custom_field_values
        ALTER COLUMN value_date TYPE TIMESTAMPTZ
        USING (value_date::timestamp at time zone 'UTC')
    """)
```

**Safety:** the cast is lossy (drops time-of-day component). Confirm no app code relies on the timestamp before merging.

### Optional — `20260502_dead_letter_webhook_deliveries.py` (EVT-6)

Deferred. Sketch only:
```sql
CREATE TABLE dead_letter_webhook_deliveries (
    id SERIAL PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    payload_json TEXT NOT NULL,
    last_error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    replayed_at TIMESTAMPTZ
);
```

---

## 9. Suggested Tests

| Layer | Test | Rationale |
|---|---|---|
| API + Tenant | `test_bulk_action_rejects_other_tenant_ids` | Catches TEN-1 regression |
| API + Tenant | `test_approval_history_rejects_other_tenant` | TEN-2 |
| API + Tenant | `test_compare_quotes_rejects_other_tenant` | TEN-3 |
| API + Tenant | parameterized `test_response_includes_tenant_id` for quotes/customers/opportunities | Q-2, CU-3 |
| Realtime | `test_lead_score_change_emits_domain_event` | EVT-1 |
| Realtime | `test_opportunity_score_change_emits_domain_event` | EVT-2 |
| Realtime | `test_event_bus_handler_failure_captured_to_sentry` | EVT-3 |
| API contract | `test_paginated_endpoints_use_canonical_envelope` (parameterized over a list of paths) | A-4/A-5/A-6 |
| API contract | `test_post_invoice_from_quote_returns_full_dict` | A-8 |
| Frontend render | RTL test for `LeadDetailPage` asserting `score_breakdown` factors render | F-5 |
| Frontend render | RTL test for `KpiStrip` asserting `signal_stats.critical_count` is visible | F-4 |
| Frontend render | RTL test for `AtRiskCustomersCard` asserting recommendations render | F-3 |
| Schema | `test_no_unintended_nullable_columns_in_feature_store` | DB-2/DB-3 |

---

## Final summary lists

- **DB columns not used by backend:** none confirmed in this round
- **Backend model fields not backed by DB:** none confirmed (Q-1 from round-1 was the only known one)
- **Backend fields not exposed through API:** Q-2 (`Quote.tenant_id`), CU-3 (`Customer.tenant_id`)
- **API fields never consumed by frontend:** F-3, F-4, F-5, F-6, F-7, F-8, F-9, F-10, F-11, F-12, plus 4 honorable mentions
- **Frontend fields/types missing from API/backend:** TS-1 (NaN), TS-2 (loose generic), TS-4 (territory join)
- **Data fetched but not rendered:** 12 confirmed (F-1…F-12)
- **UI components showing incomplete data:** AtRiskCustomersCard, KpiStrip, LeadDetailPage, BuyerRelationshipMap StakeholderCard, SubscriptionDetailPage, ActivityLogPanel, CoachingRepPage, InsightsPage, CustomerCard, CustomerDetailPage form
- **Realtime events emitted but not handled:** none confirmed in this round (round-1 found the publish-without-subscriber set already)
- **Realtime events handled / defined but never emitted:** EVT-1 (lead.score_changed), EVT-2 (opportunity.score_changed)
- **Schema/type/nullability mismatches:** DB-1 (DomainEvent), DB-2/DB-3 (V5/V6 nullability), DB-5 (Date vs DateTime)
- **Permission / feature-flag mismatches:** TEN-1, TEN-2, TEN-3, X-6 (4 sidebar flags missing from allow-list)
- **Required migrations:** 1 mandatory (DB-5), 1 conditional (DB-1), 1 deferred (EVT-6)
- **Recommended frontend type updates:** Customer (tenant_id), Quote (tenant_id), Lead (score_breakdown structure), CustomerHealthReport already done in round-1
- **Recommended backend DTO/serializer updates:** quotes._quote_to_dict (Q-2), customers._customer_to_dict (CU-3), invoices._invoice_to_dict (A-8), invoice.paid event payload (A-9)
- **Recommended tests:** 13 (per section 9)

---

## Methodology

Six parallel `Explore`/`general-purpose` subagents, each scoped to one layer:

1. **DB ↔ Backend ORM** — migrations vs models, type/nullability/index/relationship drift
2. **Backend ↔ API contract** — DTO completeness, response shapes, pagination envelopes, enum exposure
3. **API ↔ Frontend client** — TS type drift, defensive fallbacks, generic-typed responses
4. **Data fetched but not rendered** — JSX vs query data, partial renders, write-only form fields
5. **Realtime + state lifecycle** — publish/subscribe pairing, payload validation, exception handling
6. **Permissions + feature flags + naming** — `assert_same_tenant` coverage, role-check consistency, flag allow-list

Each agent constrained to evidence-backed findings with `file:line` references. Agents 1, 3, and 6 produced some claims that I judge as needing manual verification (flagged inline). The headline cross-tenant findings (TEN-1, TEN-2, TEN-3) were re-verified by direct file read after the agents returned.

No code modified per the explicit "do not modify files unless asked" rule from the audit prompt.
