# Round-14 cross-layer audit — 2026-05-13

**Scope.** Honeywell Sales Suite, deploy branch `deploy/render-sandbox`, HEAD `5fb753c` (post Round-13 closeout). Cross-layer pass: DB ↔ ORM ↔ Service ↔ API ↔ Frontend ↔ UI.

**Prior context.** Rounds 5–13 closed 200+ findings; latest sprints typed every list endpoint to `PaginatedResponse[T]` and wired per-entity `response_model=` on the 9 tier-1/2 entities. Round-14 sweeps for *new* regressions and the long-tail items prior rounds chose not to chase.

**Method.** Static analysis (grep / ast across 27.8k LOC backend + 47.6k LOC frontend), schema-check run, SPA type-check, full pytest run (846 pass minus pre-existing SQLite drift). No live database state inspected.

**Headline.** One critical cross-tenant gap on the forecast-adjustments router. Everything else is medium / low maintenance work. The codebase is broadly healthy.

---

## Findings — 12 total

| ID | Severity | Layer | Title |
|---|---|---|---|
| R14-AUTH-1 | **CRITICAL** | API ↔ Service | ForecastService skips opportunity tenant check on adjustments |
| R14-AUTH-2 | HIGH | API | dashboard_builder raises 403 instead of 404 for foreign-owner access |
| R14-FE-1 | HIGH | Frontend | 137/172 useQuery hooks still lack isError UI |
| R14-CACHE-1 | HIGH | Frontend | 173 ad-hoc invalidateQueries vs 16 centralized helper imports |
| R14-API-1 | MEDIUM | API | 48 endpoints across 34 routers still use PaginatedResponse[dict] |
| R14-DB-1 | MEDIUM | DB ↔ ORM | SQLite schema-drift gate failing on TIMESTAMPTZ/DATETIME mismatch |
| R14-I18N-1 | MEDIUM | Frontend | 12 hardcoded TR strings remain in feature pages |
| R14-A11Y-1 | MEDIUM | Frontend | focus:outline-none without focus:ring replacement (banned pattern) |
| R14-TS-1 | MEDIUM | Frontend | 42 `as unknown as` / `as any` type-cast escape hatches |
| R14-LOG-1 | LOW | Frontend | 1 production `console.error` in ReportBuilderPage |
| R14-TODO-1 | LOW | Cross | 7 unresolved TODO/FIXME markers in production code paths |
| R14-RBAC-1 | LOW | Backend tests | 5 skipped security-hardening tests blocked on httpx cookie jar |

---

## Critical

### R14-AUTH-1 — ForecastService skips opportunity tenant check (CRITICAL)

**Where.** [`backend/app/services/forecast_service.py:63-104`](../../backend/app/services/forecast_service.py#L63-L104) (`create_adjustment`) and [`backend/app/services/forecast_service.py:106-113`](../../backend/app/services/forecast_service.py#L106-L113) (`get_adjustments`). Router callers: [`backend/app/api/v1/forecast.py:132`](../../backend/app/api/v1/forecast.py#L132) and [`backend/app/api/v1/forecast.py:151`](../../backend/app/api/v1/forecast.py#L151).

**Risk.**
- `POST /api/v1/forecast/adjustments` — a `sales_manager` from tenant A can post an adjustment to any opportunity in tenant B by including the opportunity_id in the body. The router calls `ForecastService(db).create_adjustment(opp_id=data.opportunity_id, ...)` without first calling `assert_same_tenant(opp, current_user)`. The service loads the opportunity by id alone (`select(Opportunity).where(Opportunity.id == opp_id)`), applies the new amount, and persists. Tenant A's manager just mutated tenant B's forecast.
- `GET /api/v1/forecast/adjustments?opportunity_id=N` — same lookup, returns the full adjustment history (manager comments, dollar deltas) for any tenant's opportunity.

**Why it's critical.** Forecast amounts feed pipeline reporting and revenue dashboards. A cross-tenant write here can corrupt a competitor's revenue projection; a cross-tenant read leaks deal pipeline. Both surfaces are reachable by any authenticated `sales_manager` who knows / can enumerate an opportunity id.

**Fix sketch.** In both `create_adjustment` and `get_adjustments`, take `current_user` and call `assert_same_tenant(opportunity, current_user, exception_cls=NotFoundException)` after the opportunity load. Update both router handlers to thread `current_user` through. Existing pattern: see `deal_rooms._assert_opp_in_tenant` (R5-TEN-26) for a clean precedent.

**Test.** Add `test_round14_forecast_tenant_guard.py` driving `assert_same_tenant` against tenant A's user + tenant B's opportunity → expect `NotFoundException`. Mirror R12-AUTH-3's structure.

---

## High

### R14-AUTH-2 — dashboard_builder raises 403 instead of 404 (HIGH)

**Where.** [`backend/app/api/v1/dashboard_builder.py:230-244`](../../backend/app/api/v1/dashboard_builder.py#L230-L244):

```python
async def _get_user_dashboard(db, dashboard_id, current_user) -> DashboardConfig:
    result = await db.execute(select(DashboardConfig).where(DashboardConfig.id == dashboard_id))
    dashboard = result.scalar_one_or_none()
    if dashboard is None:
        raise NotFoundException("Dashboard bulunamadi")
    if dashboard.owner_id != current_user.id:
        raise ForbiddenException("Bu dashboard'a erisim yetkiniz yok")  # ← should be 404
    return dashboard
```

**Risk.** Per CLAUDE.md "Cross-tenant access maps to 404, not 403 — never leak existence of foreign-tenant rows." The 403 response confirms to an attacker that a dashboard with that id exists, just owned by someone else. The 404 hides this.

**Secondary.** `DashboardConfig` has no `tenant_id` column — owner-id-only enforcement assumes user_id is globally unique across tenants. Theoretically possible to collide after user-import; not exploitable today.

**Fix.** Change `ForbiddenException` → `NotFoundException`. Optional follow-up: add `tenant_id` column to `DashboardConfig` and migrate `_get_user_dashboard` to use `scoped_for_user` + tenant assertion.

### R14-FE-1 — 137/172 useQuery hooks lack isError UI (HIGH)

**Where.** Sweep across `frontend/src/features/`. The Sprint 4 closeout wired the 14 highest-leverage panels on `CustomerDetailPage` + `OpportunityDetailPage`; the remaining 137 hooks across LeaderboardPage, BoardPage, the parts-intel surfaces, network-intelligence, planning-studio, ai-insights, etc. silently render empty on failure.

**Risk.** Operational. A backend outage on (e.g.) `/api/v1/leaderboard/` makes the leaderboard render as "no rows" rather than offering a retry. Looks like a data problem; is actually an outage.

**Fix.** Continue the Sprint 4 pattern: destructure `isError + refetch`, render `<QueryErrorBanner onRetry={() => refetch()} />`. The primitive already exists. ~10 medium-traffic pages × 5–15 queries each.

### R14-CACHE-1 — 173 ad-hoc invalidateQueries calls vs 16 centralized imports (HIGH)

**Where.** `frontend/src/features/**/*.tsx`. 173 inline `queryClient.invalidateQueries({ queryKey: [...] })` versus 16 imports of `frontend/src/lib/cacheInvalidation.ts`.

**Risk.** CLAUDE.md mandate: "Mutation invalidation goes through `lib/cacheInvalidation.ts` helpers, not ad-hoc `invalidateQueries`. Cross-feature invalidations belong in the helper, not in the component." 91% of mutations bypass the helper. Closing a deal should invalidate kanban + dashboard + reports + cockpit + forecast; the inline call likely hits only the originating page's keys, leaving stale data on the others until a manual refresh.

**Fix.** Add a CI lint (eslint rule or grep gate): "no `invalidateQueries(` outside `lib/cacheInvalidation.ts`". Then a multi-PR migration moving the inline calls into named helpers (`onOpportunityChanged`, `onCustomerChanged`, etc.) that already exist for some entities.

---

## Medium

### R14-API-1 — 48 endpoints across 34 routers still use PaginatedResponse[dict] (MEDIUM)

**Where.** `grep -rln 'PaginatedResponse\[dict\]' backend/app/api/v1/` returns 34 files: `activities`, `reports_v2`, `leaderboard`, `revenue_recognition`, `forecast`, `users`, `customer_health`, `audit`, `approvals`, `compliance`, `network_intelligence`, `teams`, `guided_selling`, `emails`, `custom_fields`, etc. — 48 total endpoints.

**Risk.** OpenAPI ships untyped list items, so SDK codegen produces `Record<string, unknown>[]` for these surfaces and SPA consumers paper over with `as` casts. Discovery and refactor confidence suffer.

**Fix.** Sprint 6c equivalent: per-router pass to introduce `<Entity>Response` schemas where the entity is well-defined. Some (`audit`, `compliance`, `analytics`-shaped responses) are intentionally dict-shaped (heterogeneous rows); document those with a comment instead.

### R14-DB-1 — schema-drift gate failing locally on SQLite TIMESTAMPTZ/DATETIME (MEDIUM)

**Where.** `backend/tests/test_schema_drift.py::test_no_schema_drift_against_test_db`. Failing on every CI run + local run with `TEST_DATABASE_URL=sqlite+aiosqlite:///./test.db`. Reports 50+ "type mismatch: X model=TIMESTAMPTZ db=DATETIME" entries.

**Risk.** False negative: the schema-drift CI gate is supposed to catch real ORM-vs-DB drift on Postgres. A persistent SQLite false-positive means the gate's signal-to-noise is broken. Real drift now hides behind the existing noise.

**Fix.** Either:
1. Make the drift checker dialect-aware: skip TIMESTAMPTZ comparisons when the connected DB is SQLite (which has no native timezone type).
2. Run the gate exclusively against the Postgres test fixture (docker-compose `db-test`) and skip on SQLite.

Option 2 is the standard pattern. The two `pytest.skip(...)` calls already in the test file show this was the intent.

### R14-I18N-1 — 12 hardcoded TR strings remain in feature pages (MEDIUM)

**Where.** `BoardPage` ("Fırsat yok"), `ActivityLogPanel` ("Henüz aktivite kaydedilmemis"), `CommentThread` ("Henüz yorum yok"), `AiAttributeValuesPanel` ("Henüz değer üretilmedi"), `LeaderboardPage` ("Henüz rozet kazanılmamış"), `EmailDetailPage` ("Müşteri:"), `TerritoryPage` ("Henüz bölge yok"), `PlaybookDetailPage` (3× inline help text), `AiInsightsPage` (3× select option labels).

**Risk.** Same as the R13 Sprint 5 set — EN users see Turkish chrome on these surfaces. Lower visibility than the ones Sprint 5 caught; long tail.

**Fix.** Same pattern as Sprint 5. Extract to existing `common.no_data` / `common.empty_state` keys or add `ai_insights.entity_type_*` keys for the select options.

### R14-A11Y-1 — focus:outline-none without focus:ring replacement (MEDIUM)

**Where.** `frontend/src/features/settings/SettingsPage.tsx` has 2+ inputs with `focus:outline-none focus:border-honeywell-red` and no `focus:ring`. Same pattern in `PipelineSettingsPage`, `InvoiceListPage`, `ChatWidget`, `AgentChatPage`.

**Risk.** Per CLAUDE.md banned patterns: "`outline: none` without a replacement focus indicator." Border color alone fails WCAG 2.4.7 (focus visible) — color-only differentiation is insufficient at low contrast, and a sighted-but-keyboard-only user loses orientation.

**Fix.** Add `focus:ring-[3px] focus:ring-honeywell-red/20` alongside the existing `focus:border-honeywell-red`, matching the canonical input pattern in `frontend/src/components/ui/Input.tsx`.

### R14-TS-1 — 42 `as unknown as` / `as any` type-cast escape hatches (MEDIUM)

**Where.** 42 instances across `frontend/src/features/` + `frontend/src/components/`. Samples:
- `CommentThread.tsx`: `usersData as unknown as User[]`
- `ReportsPage.tsx`: 2 casts to `NoPricePart[]` / `{ items: NoPricePart[] }`

**Risk.** Each cast bypasses TypeScript's protection. Most are response-shape papering — exactly the kind of casts that the Sprint 6a/6b typed-response work was meant to retire.

**Fix.** As each list endpoint moves to a typed `PaginatedResponse[<EntityResponse>]`, drop the corresponding `as unknown as` cast at the call site. Add an ESLint rule banning `as unknown as` outside `lib/` and test files.

---

## Low

### R14-LOG-1 — 1 production console.error (LOW)

**Where.** [`frontend/src/features/reports/ReportBuilderPage.tsx:155`](../../frontend/src/features/reports/ReportBuilderPage.tsx#L155): `console.error('Preview error:', apiErr?.response?.data || err);`.

**Fix.** Replace with toast.error or a logged-elsewhere telemetry call. Per the typescript coding-style rule "No console.log statements in production code."

### R14-TODO-1 — 7 unresolved TODO/FIXME markers (LOW)

**Where.**
- `models/territory.py`, `models/team.py`, `models/product_bundle.py`, `models/pricing.py` — "TODO: backfill in alembic 20260504_phase4_tenant". Stale; the migrations exist.
- `api/v1/emails.py`: `"matches": []  # TODO: Populate from part matching service`. Public API surface returning a placeholder.
- `components/layout/QuickAddFAB.tsx`: notes integration deferred.

**Fix.** Delete the stale TODOs in the four model files (migrations are merged). The emails-matches TODO is a real gap — either wire the part-matching service or document as out-of-scope.

### R14-RBAC-1 — 5 skipped security-hardening tests (LOW)

**Where.** `backend/tests/test_security_hardening.py` — 3 tests skipped on httpx ASGITransport cookie jar limitation ("verified via live curl test"). No automated regression net for the cookie-auth security behaviour.

**Fix.** Re-implement using a proper test client that supports cookie persistence (e.g., `httpx.AsyncClient` with explicit cookie state) or convert to a Playwright/curl smoke run that gates CI on the security-relevant cookie flow.

---

## Metrics (current state)

| Surface | Count | vs Round 13 |
|---|---|---|
| Typed list endpoints (`PaginatedResponse[T]`) | 67 | +0 |
| Untyped list endpoints (`PaginatedResponse[dict]`) | 48 | (newly counted) |
| Typed item endpoints (per-entity `response_model`) | 40 | +0 |
| Pydantic response schemas | 17 | +0 |
| Backend tests passing | 846 / 856 collected | stable |
| Backend tests skipped (real coverage gap) | 5 | stable |
| Frontend `useQuery` hooks | 172 | (newly counted) |
| Frontend `useQuery` hooks with isError UI | ~35 (~20%) | (newly counted) |
| Frontend `invalidateQueries` ad-hoc / centralized | 173 / 16 | (newly counted) |
| Frontend `as unknown as` / `as any` casts | 42 | (newly counted) |
| EN ↔ TR i18n key parity | 2197/2197 (100%) | stable |
| Backend hardcoded TR error strings (intentional) | ~40 | unchanged |
| Frontend hardcoded TR strings (incidental) | 12 | -28 from R13 |
| Feature-flagged routes | 20 | stable |

---

## Sprint plan

### Sprint 14a — Critical security (1 day)

Close R14-AUTH-1 (forecast adjustments tenant guard) and R14-AUTH-2 (dashboard 403→404). Add the missing test (`test_round14_forecast_tenant_guard.py`). Single PR, blocking on merge.

### Sprint 14b — Hardcoded TR + accessibility sweep (2 days)

Close R14-I18N-1 (12 hardcoded strings) + R14-A11Y-1 (focus:ring replacements on the 5 named surfaces). Mechanical, parallel-safe with 14a.

### Sprint 14c — Cache invalidation centralization (1 week)

Close R14-CACHE-1. Stages:
1. Add ESLint rule banning ad-hoc `invalidateQueries` in `features/`.
2. Audit existing `lib/cacheInvalidation.ts` helpers — verify they cover the cross-feature fan-out (closing a deal touches kanban + dashboard + reports + cockpit + forecast).
3. Multi-PR migration: one entity per PR, moving the call sites in.
4. Land the lint as `error` once the count hits zero.

### Sprint 14d — Schema-drift gate fix (2 days)

Close R14-DB-1. Make `test_schema_drift.py` dialect-aware (skip TIMESTAMPTZ comparisons when the connected DB is SQLite) or gate the test to require a Postgres `TEST_DATABASE_URL`. Restore CI signal.

### Sprint 14e — isError + response_model cleanup (1 week, optional)

Close R14-FE-1 + R14-API-1 + R14-TS-1 incrementally. Each new typed list endpoint retires a corresponding `as unknown as` cast on the SPA side; each new typed response retires a silently-empty `isError` surface.

### Sprint 14f — Long tail (½ day)

R14-LOG-1, R14-TODO-1, R14-RBAC-1. Mechanical cleanup.

---

## Out of scope

- Round-13 Sprint 7b alias retirement: complete; nothing remaining.
- Sprint 6a/6b per-item response_model work: complete on 9 entities (customer/quote/opportunity/lead/invoice/contract/campaign/subscription/email_template + webhook/playbook/sequence/dashboard/saved_view/shared_document).
- Orphan-row backfill runbook (`docs/runbooks/r13-orphan-tenant-backfill.md`): admin-driven; no engineering action required.

## Sequencing recommendation

**Critical-blocking:** Sprint 14a (R14-AUTH-1 + R14-AUTH-2) must land before the next release. Everything else is incremental hygiene that can ride normal release cadence.

**Parallel-safe:** 14a, 14b, 14d can run by separate hands in the same week.

**Long-running:** 14c (cache centralization) and 14e (typed-response cleanup) are multi-week and benefit from being scheduled across release cycles rather than rushed.

— end Round-14 audit
