# Production Stabilization — 2026-04-29

**Status:** Feature freeze in effect.
**Scope:** No new features until the production deploy of `a8e886a`
soaks for at least one full week without P1+ incidents and the open
operational items in §5 are resolved.
**Branch:** `deploy/render-sandbox` (HEAD: `a8e886a`)
**Migration head:** `20260428_v13_audit_tenant`

---

## 1) What "stabilize" means

For the next stabilization window the rule is:

- **No** new features.
- **No** speculative refactors.
- **Allowed:** bug fixes for production incidents, minor doc edits,
  patch-version dependency bumps that pass CI cleanly.
- **Allowed but documented:** flag flips on production (e.g. turning
  `FEATURE_V10_PARTS_INTEL=true` for a pilot) — capture the result
  in the operational log below.
- **Required before unfreeze:** P0/P1 actions in §5 are all green
  AND a clean restore drill against the V13 schema.

---

## 2) Shipped surface (what's live)

| Layer | What's in | Flag (default) | Notes |
|---|---|---|---|
| V2 | Board + tasks + opportunities | `FEATURE_V2_BOARD` (off) | Schema present |
| V4 | Feature store, deal replay, sales DNA, network benchmarks | `FEATURE_V4_*` (off) | Read-only intelligence |
| V5 | Intelligence aggregates | `FEATURE_V5_INTELLIGENCE` (off) | Composes V4 |
| V6 | Realtime recompute | `FEATURE_V6_REALTIME` (off) | Hooks into write path when on |
| V7 | LLM-hybrid objection detection | `FEATURE_V7_LLM_OBJECTION` (off) | Claude pass on top of keyword detector |
| V8 | Multi-tenant CRM (`tenant_id` on users/customers/opps/quotes/leads) | always-on (NULL = legacy) | Bootstrap script run; default tenant id=2 backfilled (42 rows) |
| V9 | CRM sync, calendar OAuth, NL search, quote revisions, slippage | per-sprint flag (off) | All schema in head |
| V10 | Spare parts intelligence (read-only derivation) | `FEATURE_V10_PARTS_INTEL` (off) | Manager-only dashboard |
| V11 | Qdrant RAG | `FEATURE_RAG` (off) | Backfill script + scheduler cron |
| V12 | Multi-tenant enforcement (list scoping + 404 cross-tenant guard) + transformer sequence embedding | always-on / `FEATURE_TRANSFORMER_SEQ_EMBEDDING` (off) | E2E tests cover scoping |
| V13 | `audit_logs.tenant_id` (forensics) + cross-tenant Sentry/Prometheus signals + 6 V4 endpoint guards | always-on (NULL = legacy) | Migration is idempotent |

---

## 3) Test inventory

- **Backend pytest:** ~787 tests, 3 skipped, **PostgreSQL test DB**
  on `localhost:5434`. Single pre-existing flaky fixture in
  `test_forecast_service::test_take_pipeline_snapshot` (unrelated to
  stabilization scope, tracked in P3 backlog).
- **Frontend:** vitest 36/36, tsc clean, build OK
  (~659 kB index bundle / ~189 kB gzipped after vendor split).
- **Test files:** 94 backend + 7 frontend.
- **Runbooks:** 19 markdown files under `docs/runbooks/`.
- **Feature flags:** 57 declared in `config.py`, all listed in
  `.env.example` and `docs/feature-flags.md`.

---

## 4) Operational invariants

These are the contracts the deploy depends on. Don't break without
explicit sign-off.

| Invariant | Where it lives | Why |
|---|---|---|
| `ENCRYPTION_KEY` is `sync: false` in `render.yaml` | render.yaml:38 | Regenerating loses KVKK PII decryption irreversibly |
| `AUTO_CREATE_TABLES=false`, `AUTO_SCHEMA_SYNC=false` in prod | render.yaml | Schema drift via Alembic only |
| `tenant_id` columns are nullable on legacy tables | V8/V12/V13 migrations | Single-tenant deployments stay working |
| Alembic revision IDs ≤32 chars | new migrations | `alembic_version.version_num` is `varchar(32)` (lesson from V13 deploy fail) |
| `get_redis()` returns `None` permanently | redis_client.py | All callers degrade to in-memory |
| `assert_same_tenant` always fires the Prometheus counter + Sentry breadcrumb | tenant_context.py | SOC needs the signal even though API returns 404 |
| `FEATURE_*` flags default off in code AND env | config.py + .env.example | Safe-by-default rollout |

---

## 5) Open operational items (must-fix before unfreeze)

### Must-do (operator action required)

1. **Set `STAGING_DATABASE_URL` repo secret** so the monthly restore
   drill can run. Until this is done, the V9/V10/V12/V13 schema is
   never restored against a backup → DR posture is unverified.
   - Path: GitHub → Settings → Secrets → Actions → New
   - Value: Render staging DB external URL (must be a separate DB
     from prod — drill will overwrite it)
   - Then trigger: `gh workflow run restore-drill.yml`

2. **Verify Render deploy of `a8e886a` succeeded.** The previous
   deploy of the long-revision-name V13 left prod in a half-applied
   state (DDL ran, version pointer didn't move). The rename in
   `d3f6f42` makes the migration idempotent so re-running is safe;
   confirm via:
   ```bash
   gh workflow run manual-migrate.yml --ref deploy/render-sandbox -f confirm=MIGRATE
   ```
   Expected `alembic current` = `20260428_v13_audit_tenant`.

3. **Remove `REDIS_URL` env from Render dashboard** if it was set
   manually for the previous (Redis-on) deploy. The app ignores it
   now but a stale value confuses operator audits. Same for
   `REDIS_PASSWORD`.

### Should-do (operator review)

4. **Cross-tenant alert rule** in Grafana / Sentry on
   `rate(hsm_cross_tenant_blocked_total[5m]) by (user_id) > N`. The
   counter is wired; the alert kuralı henüz kurulu değil.

5. **Per-tenant SLOs** — V12 multi-tenant ships with one tenant
   (`Honeywell TR`, id=2). When a second tenant onboards, split the
   existing SLOs by tenant label.

### Nice-to-have (P3 backlog)

- Frontend `api.ts` split into per-feature modules (parked: 31kB
  gzip is acceptable, ROI is low).
- Cross-tenant probe SOC playbook + suspend-user runbook.
- V12 yan endpoint'lerine guard yayma — şu an
  `timeline / activity-summary / deal-room / comments` korumasız
  (parent endpoint korumalı olduğu için sızıntı sınırlı ama
  defensive layer henüz tam değil).

---

## 6) Production deploy checklist

Each deploy under stabilization mode must:

- [ ] CI green on `deploy/render-sandbox` HEAD (all 6 jobs pass).
- [ ] Last 3 alembic revisions ≤32 chars.
- [ ] `git status` clean (no uncommitted secrets or scratch files).
- [ ] No new `FEATURE_*` flag default flipped to `true` in
      `config.py` (prod flag flips happen via Render dashboard, not
      code).
- [ ] If touching the schema: `alembic upgrade head` then
      `alembic downgrade -1` test on PG locally.
- [ ] If touching `assert_same_tenant`, `get_redis`, or
      `audit_service.log_action`: a corresponding test was added or
      updated.

---

## 7) How to lift the freeze

Drop this section into the unfreeze PR description:

> Stabilization window ended on YYYY-MM-DD. All P0/P1 items in
> `docs/STABILIZATION-REPORT.md §5` are resolved. The most recent
> restore drill ran on YYYY-MM-DD and passed. Production has had
> zero P1 incidents since `a8e886a` deployed on YYYY-MM-DD.
> Resuming feature work on the V14 backlog.

Until that PR merges, this document is the blocking reference.
