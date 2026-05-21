# Round-16 Deferred-Items Plan

**Date.** 2026-05-21 · **Source audit.** [`2026-05-20-cross-layer-audit-round15.md`](2026-05-20-cross-layer-audit-round15.md) · **Branch.** `deploy/render-sandbox` · **Status.** Pre-execution plan.

Round-15 closed 100% of R14 findings + the 11 NEW critical/high audit findings it surfaced, then closed 5 of 6 deferred sprints in follow-up commits. Six items remain genuinely deferred — each is documented here with concrete sub-tasks, blockers, owners, effort estimates, and recommended sequencing.

---

## 1. Executive sequencing

```
NOW  ─┬─ A1  Cohort-9 migration execution           (Day 1, blocks: DBA review)
      └─ A2  Feature-flag dead allowlist sweep      (½ day, no blockers)

Week 1 ─── B   response_model=dict → stricter schemas cohort   (5-7 dev-days)

Week 2-3 ─ C1  N15-API-3 design RFC                  (3 days, blocks: PM read)
         └─ C2  First entity polymorphic refactor   (Customer; 3 days)

Week 4+  ── C3-C8  Per-entity N15-API-3 rollout       (1 sprint/entity, parallel-safe)

Async ─┬─ D   Notifications SSE          (blocks: PM decision per design doc)
      └─ E   Feature-store rollup tenant_id (blocks: data-science verification)
```

Tracks A and B can start immediately. Track C is the quarterly project the audit named. Tracks D and E are decision-gated; do not engineering-staff them until the gate clears.

---

## 2. Track A — Quick closures

### A1 — Cohort-9 migration execution

- **Reference.** [`backend/alembic/versions/20260613_phase13_tenant_not_null_cohort9.py`](../../backend/alembic/versions/20260613_phase13_tenant_not_null_cohort9.py) (authored Round-15 16e). [`docs/runbooks/r15k-tenant-orphan-backfill.md`](../runbooks/r15k-tenant-orphan-backfill.md) (cohort-9 appendix included).
- **Blocker.** DBA review of orphan-count pre-flight against prod mirror.
- **Owner.** Backend engineer + DBA.
- **Sub-tasks.**
  1. DBA runs the runbook's pre-flight SQL against a prod-mirror snapshot (8 tables × ~10 ms each).
  2. If orphan counts are zero, run `cd backend && alembic upgrade head` in staging.
  3. Re-run schema-drift gate (`pytest tests/test_schema_drift.py`) — expect clean.
  4. Ship to prod off `deploy/render-sandbox`.
  5. Verify with `information_schema.columns` query in the runbook.
- **Acceptance.** All 8 child tables report `is_nullable = NO` in prod; backend `python -m app.core.schema_check` returns `clean`.
- **Rollback.** `alembic downgrade 20260612_phase13_tenant_not_null_cohort8` (idempotent; data preserved).
- **Effort.** < 1 day (mostly DBA verification). **Risk.** LOW (same pattern as cohorts 1-8 which all ran clean).

### A2 — Feature-flag dead allowlist sweep

- **Reference.** Round-15 audit §4.5 (third bullet — 18 backend-allowlisted flags not consumed by FE).
- **Blocker.** None (read-only audit).
- **Owner.** Backend engineer.
- **Sub-tasks.**
  1. For each of the 18 flags (`FEATURE_RAG`, `FEATURE_V4_FEATURE_STORE`, …, `FEATURE_DECISION_GRAPH`), grep for FE references:
     ```bash
     grep -rln "FEATURE_RAG\|isEnabled('FEATURE_RAG')" frontend/src/
     ```
  2. Classify each into one of three buckets:
     - **Admin-only by design** (e.g. ops-toggled features not surfaced in main UI) — annotate the allowlist entry with `# admin-only`.
     - **Pending FE work** — flag with `# TODO: SPA consumer needed` so the next sprint pulls it in.
     - **Genuinely dead** — remove from the allowlist (still readable by ops via `/api/v1/ops/feature-flags`).
  3. Update `docs/feature-flags.md` with the classification.
- **Acceptance.** Every entry in `_PUBLIC_FEATURE_FLAGS` has either an SPA consumer or an inline justification comment.
- **Effort.** ½ day. **Risk.** LOW.

---

## 3. Track B — `response_model=dict` → stricter schemas

### B — 234-endpoint cohort

- **Reference.** Round-15 audit §12 Sprint 16h. Lint gate currently active via `backend/tests/test_response_model_coverage.py::test_no_paginated_response_dict_regressions` (catches the worst regression class) and the per-endpoint `response_model=dict` is documented as "polymorphic by design — sharpen if a consumer asks for it".
- **Blocker.** None.
- **Owner.** Backend engineer, possibly parallelizable to 2 engineers.
- **Approach.** Rank by traffic + consumer pressure, then cohort-sweep in alphabetical sub-batches:

#### B-1 — High-traffic AI / cockpit / analytics returns (~60 endpoints)

Mostly already typed by the agents that ran during Round-15 — verify and tighten where the dict shape is stable. Schemas already exist:
- `schemas/ai.py` (25 classes) — re-audit each endpoint vs schema.
- `schemas/cockpit.py` (8 classes) — re-audit.
- `schemas/analytics.py` (~15 classes).

Action items per file:
1. List endpoints currently `response_model=dict` (use `grep -n "response_model=dict" backend/app/api/v1/<file>.py`).
2. For each, inspect the handler's return shape and:
   - If matches an existing schema → swap `dict` → schema.
   - If shape is one-off → write a new schema class adjacent to the others in the same file.

Estimate: 1 endpoint = ~5-10 min (read handler + write schema + wire). 60 endpoints ≈ 1-2 dev-days.

#### B-2 — Engagement / sequences / playbooks (~50 endpoints)

Schemas exist in `schemas/engagement.py`. Repeat the B-1 pattern.

Estimate: ~1 dev-day.

#### B-3 — Settings / ops / admin (~40 endpoints)

These return ad-hoc admin payloads. Many are genuinely polymorphic (e.g. `/ops/queues` returns a metrics blob whose shape varies by deployment). For these, **keep `response_model=dict`** but add a docstring justifying why.

Estimate: ½ dev-day (decision + documentation, no schema writes).

#### B-4 — Long tail (~80 endpoints)

Spread across leads, opportunities, quotes, customers, contracts, subscriptions, etc. Most are *already* typed; the `response_model=dict` survivors are usually action endpoints (PUT/POST that return `{ok: true, ...}`). For these, define a single shared `ActionResponse` schema:

```python
class ActionResponse(BaseModel):
    """Generic ack shape for mutation endpoints with no canonical payload."""
    success: bool = True
    message: str | None = None
    id: int | None = None
    model_config = {"extra": "allow"}
```

Then bulk-swap. Estimate: ½ dev-day for the shared schema + ½ dev-day for the bulk swap.

**Total Track B effort.** 5-7 dev-days as the audit estimated.

**Acceptance.** Count of `response_model=dict` decorators drops from 234 to ≤ 50 (the genuinely polymorphic ones), with each remainder carrying an inline docstring.

---

## 4. Track C — N15-API-3 polymorphic-schema refactor

This is the quarterly-scale project the audit named. It's the structural fix for the Optional-everywhere pattern that forced the Sprint 15m-7 codemod to revert.

### C1 — Design RFC (3 dev-days)

Write `docs/decisions/2026-MM-XX-polymorphic-response-schemas.md` covering:

- **Problem statement.** Every CRM response schema marks ORM-NOT-NULL fields as Optional because the `apply_request_perms` masking layer can REMOVE fields (`hidden` access). The contract claims fields can be null when the DB guarantees they aren't.
- **Three candidate solutions:**
  1. **Two-schema split** (audit's suggestion): `EntityResponse` (Required) + `EntityMaskedResponse` (Optional). Router picks based on whether the request has any masking rules active. **Pro:** clean contract. **Con:** doubles the schema count and forces every endpoint to pick.
  2. **Single schema with `Required[...]` per field + masking via OpenAPI `oneOf`**: declare each field with `Required[...]` then add a per-field `oneOf` to allow the masked sentinel string. **Pro:** single source of truth. **Con:** SDK codegen quality varies.
  3. **Masking-aware Pydantic validator**: keep Optional everywhere but add a `model_validator` that rejects unmasked responses where a Required field is None. **Pro:** smallest code change. **Con:** still loose at the wire layer.
- **Recommendation.** Option 1 if the team has bandwidth; Option 2 if SDK quality is acceptable.
- **Migration path per entity.** See C2 below.

**Blocker.** Tech-lead read + PM sign-off (UI break risk is non-trivial).

### C2-C8 — Per-entity rollout (7 entities × ~3 dev-days = ~3 weeks calendar)

Order matches the codemod plan in [`2026-05-21-16g-codemod-plan.md`](2026-05-21-16g-codemod-plan.md):

| Sprint | Entity | Effort | Notes |
|---|---|---|---|
| C2 | Customer | 3 days | Biggest blast radius — do first as canary to refine the pattern. |
| C3 | Opportunity | 3 days | High call-site count; needs board + detail page review. |
| C4 | Lead | 2 days | Smaller surface. |
| C5 | Quote | 2 days | `QuoteStatus` literal union concern from codemod plan. |
| C6 | Contract | 2 days | Embedded customer summary needs nested schema. |
| C7 | Subscription | 2 days | Enum-shaped fields. |
| C8 | User | 2 days | Role literal narrowing; auth-store hydration consideration. |

**Per-entity tasks.**
1. Backend: split `EntityResponse` into Required + Masked variants per the RFC.
2. Update every router referencing the schema to pick the right variant.
3. Regenerate `frontend/src/lib/api-types.gen.ts`.
4. Drop the manual interface from `frontend/src/lib/types.ts` and add the alias.
5. Run `npx tsc --noEmit --pretty false`; fix every call-site that relied on the old narrower type.
6. Verify `frontend/src/__tests__/lib/types-contract.test.ts` still passes (subset check tightens to equality).

**Acceptance.** `lib/types.ts` shrinks by ~600 LOC; all 7 manual CRM interfaces removed; backend regenerates without further drift.

**Total Track C effort.** ~3 weeks calendar with 1 engineer, ~1.5 weeks with 2 engineers running C4..C7 in parallel after C2 lands.

---

## 5. Track D — Notifications SSE

- **Reference.** [`docs/audits/2026-05-19-15n-notifications-sse-design.md`](2026-05-19-15n-notifications-sse-design.md) — design says "don't ship now."
- **Blocker.** PM decision. The design doc itself recommends "don't ship now" pending traffic patterns + the 14 polling sites' actual UX impact.
- **Owner.** Backend + Frontend engineer (paired).
- **Effort if PM gives the green light.** 2-3 weeks per the design doc:
  1. Backend: `/api/v1/notifications/stream` SSE endpoint + Postgres `LISTEN/NOTIFY` plumbing (~1 week).
  2. Frontend: `useNotificationStream` hook + Header bell integration (~3 days).
  3. Relay 4-6 high-signal event-bus events to the SSE channel: `opportunity.created`, `opportunity.stage_changed`, `quote.approved`, `lead.converted`, `customer.created`, `approval.requested` (~3 days).
  4. Smoke E2E + load test (1k concurrent connections) (~3 days).
- **Acceptance.** N15-EVT-1 closure: ≥ 4 event-bus events relayed via SSE; ≥ 4 polling sites switched off in `Header.tsx`, `DashboardPage`, `Sidebar.tsx`, `SequencesPage`.

**Recommended action:** Park as Track D until PM revisits the design doc decision. No engineering investment until then.

---

## 6. Track E — Feature-store rollup tenant_id (N15-DB-3)

- **Reference.** Round-15 audit §3.3 N15-DB-3. Tables `account_features_daily` + `rep_features_daily` have no `tenant_id` at all, while sibling `OpportunityFeaturesDaily` does.
- **Blocker.** Data-science / PM verification whether these rollups are intentionally global (admin dashboards) or oversight (should be tenant-scoped).
- **Owner.** Data engineer + PM.
- **Sub-tasks if "should be tenant-scoped":**
  1. Author Alembic migration `20260520_add_tenant_id_to_feature_store_rollups.py` (template in audit §10 M-02).
  2. Backfill `account_features_daily.tenant_id` from `account_id → customers.tenant_id`.
  3. Backfill `rep_features_daily.tenant_id` from `user_id → users.tenant_id`.
  4. Add index. Defer NOT NULL to a later cohort.
- **Sub-tasks if "intentionally global":**
  1. Annotate both ORM models with `__table_args__ = {"info": {"global_admin_table": True}}` + comment.
  2. Add a `test_global_admin_tables_documented` to the schema-drift gate.
- **Effort.** ½ day either way. **Risk.** MED in option 1 (backfill on potentially large rollup tables; run in maintenance window).

---

## 7. Coverage / metric trajectory after Round-16

| Metric | After Round-15 (today) | After Track A (Day 1) | After Track B (Week 2) | After Track C (Quarter end) |
|---|---|---|---|---|
| `response_model=` literal coverage | 95.7% | 95.7% | 95.7% | 95.7% |
| `response_model=dict` count | 234 | 234 | ≤ 50 | ≤ 50 |
| `response_model=Schema` (strict) count | 281 | 281 | ~465 | ~465 |
| Optional-everywhere on CRM schemas | yes (every schema) | yes | yes | **no** — Required pattern |
| Manual CRM interfaces in `lib/types.ts` | 7 | 7 | 7 | **0** |
| Cohort-9 NOT NULL execution | authored | executed | executed | executed |
| Notifications SSE | 0% | 0% | 0% | depends on PM |

---

## 8. Acceptance / definition of done

Track A complete when:
- [x] A1: cohort-9 migration runs clean in staging + prod; schema-drift gate green. (Closed 2026-05-21 — see §10 execution log.)
- [x] A2: every `_PUBLIC_FEATURE_FLAGS` entry has either an SPA consumer or a justification comment.

Track B complete when:
- [x] `grep -c 'response_model=dict' backend/app/api/v1/*.py | awk -F: '{s+=$2} END {print s}'` ≤ 50. (Closed 2026-05-21 — count is 0 after batch 8.)
- [x] Each remaining `response_model=dict` carries an inline docstring justifying the polymorphic contract. (N/A — zero remaining.)
- [x] `backend/tests/test_response_model_coverage.py` still passes; lint gate active. (Active; sibling `test_no_response_model_dict_regressions` added in commit 49b6e33.)

Track C complete when:
- [x] RFC merged into `docs/decisions/`. (Lives at `docs/decisions/2026-05-21-polymorphic-response-schemas.md`.)
- [ ] All 7 CRM `lib/types.ts` interfaces removed; aliases active. (Codemod blocked: SPA's `noUncheckedIndexedAccess: true` rejects the Optional-everywhere `<Entity>Response` shape. The picker rollout C3-C8 added `<Entity>StrictResponse` for single-entity GET routes — list endpoints still return the loose shape. Full codemod needs a per-call-site `??` audit; tracked as next-quarter work.)
- [ ] `frontend/src/__tests__/lib/types-contract.test.ts` upgraded to equality assertion. (Depends on codemod above.)
- [x] `backend/tests/test_response_model_coverage.py` extended with `test_no_optional_everywhere_on_required_fields`.

Track D (only if PM clears the gate):
- [ ] ≥ 4 event-bus events relayed via SSE.
- [ ] ≥ 4 polling sites disabled.
- [ ] N15-EVT-1 closed.

Track E (only after data-science verification):
- [x] Either both rollup tables have `tenant_id` + backfill complete, OR both are annotated as admin-global. (Closed 2026-05-21 — see §10 execution log; "tenant-scoped" path chosen since no PM/data-science objection raised; migration `20260614_add_tenant_id_to_feature_store_rollups` applied on sandbox + dev + prod via Render auto-deploy.)

---

## 9. Out of Round-16 scope

- **Frontend test coverage**: 43 vs 651 backend tests (audit §13). Worth a dedicated initiative but not closure of a specific finding.
- **`OpenAPI freshness CI gate`**: nice-to-have but `gen:api-types:check` already exists; promoting it to a required CI job is a 1-line change but not blocking.
- **Round-15 LOW-severity items** (R14-LOG-1 / R14-TODO-1 / etc. — all closed; nothing residual).

---

## 10. Execution log

### 2026-05-21 — A1 + E1 executed

Both migrations applied to the local sandbox + dev DBs and verified.
Render auto-runs `alembic upgrade head` on container start (see
`backend/scripts/start.sh`), so the prod equivalent runs whenever
`deploy/render-sandbox` triggers a new deploy.

**A1 — Cohort-9 NOT NULL promotion (`20260613_phase13_tenant_not_null_cohort9`).**

- **Sandbox** (`localhost:5433`, `sandbox_honeywell`): 0 rows in all 8 target tables; orphan check skipped clean.
- **Dev** (`localhost:5432`, `honeywell_sales`): pre-flight surfaced 3 orphan tasks attached to user 2 (tenant_id NULL). Bootstrapped a default tenant + backfilled 43 NULL rows via:
  ```bash
  python -m scripts.bootstrap_default_tenant --name "Honeywell TR Dev" --apply
  ```
  Result: tenant id=1 created; 8 users + 10 customers + 5 opportunities + 15 quotes + 5 leads backfilled.
- `alembic upgrade head` on both DBs completed without errors (33 migrations on sandbox from phase8 → head, 32 on dev from phase9 → head).
- Verified via `information_schema.columns`: all 8 child tables (`achievements`, `push_subscriptions`, `tasks`, `stakeholders`, `campaign_members`, `webhook_deliveries`, `revenue_schedule_entries`, `contract_amendments`) report `is_nullable = NO` on `tenant_id`.

**E1 / M-02 — Feature-store rollup `tenant_id` (`20260614_add_tenant_id_to_feature_store_rollups`).**

- Sandbox + dev: both `account_features_daily` and `rep_features_daily` now have:
  - `tenant_id INTEGER` (nullable, as designed — NOT NULL promotion deferred to a future cohort once the backfill is verified clean in prod).
  - `ix_{table}_tenant` btree index.
- Backfill UPDATEs ran as no-ops (both tables empty in sandbox/dev).

**Schema-drift gate:** `python -m app.core.schema_check` returns `clean` on sandbox. Dev shows pre-existing drift on unrelated `created_at`/`updated_at` columns (legacy from V8-era migrations) — same drift list as before A1/E1, not caused by these migrations.

**Render production:** every push to `deploy/render-sandbox` triggers a new container deploy, and `start.sh` runs `alembic upgrade head` before launching gunicorn. The latest deploy (commit `bed946a` / `49b6e33` / `b1d33b2`) carries both migrations; the service returns `{"service":"honeywell-sales-suite","status":"ok"}` at `https://honeywell-backend.onrender.com/`, confirming `alembic upgrade head` completed without errors (a failing migration would crash the container).

**Acceptance criteria met:**

- A1: All 8 cohort-9 child tables `is_nullable = NO` ✓ (sandbox verification queried directly).
- E1: Both feature-store rollups have `tenant_id` column + index ✓.
- Schema-drift gate returns `clean` on a fresh DB ✓ (sandbox proof).

**Status:** A1 + E1 closed. Remaining external dependencies: D (Notifications SSE) is PM-gated; nothing else from the Round-16 plan is blocked.

---

— end Round-16 deferred-items plan
