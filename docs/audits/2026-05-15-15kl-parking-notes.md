# Sprint 15k / 15l parking notes — 2026-05-15

**Status.** PARKED behind a test-fixture readiness blocker.

**Origin.** `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-001
recommended promoting `tenant_id` from NULLABLE to NOT NULL on the
top-tier CRM tables (Sprint 15k cohort 1 = customers / opportunities
/ quotes / leads; Sprint 15l cohort 2 = invoices / contracts /
campaigns / subscriptions). Audit sprint board marked it
**risk: medium-high**.

---

## What was attempted

Round-15 cohort 12 work-stream attempted the promotion:

1. **Model annotation flip.** `Mapped[int | None]` → `Mapped[int]` and
   `nullable=True` → `nullable=False` on the 8 target models.
2. **Migration with belt-and-suspenders backfill.** Two migrations
   (`20260602_phase13_tenant_not_null_cohort1.py` for cohort 1 and
   `20260603_phase13_tenant_not_null_cohort2.py` for cohort 2) each
   ran a three-step pattern:
     1. Defensive backfill from the most reliable FK source
        (customer → parent customer; opportunity → parent customer
        → owner; etc.).
     2. Single-tenant fallback (`SELECT id FROM tenants ORDER BY id
        LIMIT 1`) when exactly one tenant exists in the deployment.
     3. Abort-on-residual-NULL guard via `DO $$ ... RAISE EXCEPTION
        ... $$` before `ALTER COLUMN tenant_id SET NOT NULL`.
3. **Runbook authored.** `docs/runbooks/r15k-tenant-orphan-backfill.md`
   documenting the orphan-row triage steps when the guard fires.
4. **Floor-test allowlist update** in
   `tests/test_round15_tenant_not_null_floor.py` to assert the
   newly-promoted tables stay NOT NULL.

The migration files were defensively safe — guard-on-failure, no
data loss in any branch.

## Why it was parked

Running `pytest -q` on the backend with the ORM annotations flipped
produced **172 failures and 49 errors** out of 865 tests. The
failure mode is uniform:

```
sqlalchemy.exc.IntegrityError:
  NOT NULL constraint failed: opportunities.tenant_id
[INSERT INTO opportunities (... tenant_id ...) VALUES (..., None, ...)]
```

Root cause: many individual test files create CRM rows via the
SQLAlchemy ORM directly (`Customer(...)`, `Opportunity(...)`,
`Lead(...)`, `Quote(...)`, `Contract(...)`, `Invoice(...)`,
`Subscription(...)`, `Campaign(...)`) **without** threading
`tenant_id`. The `admin_user` fixture in `tests/conftest.py` does
set `tenant_id=1` on the user, but the per-test constructors do
not propagate it to derived entities.

Sample failing call sites (representative — not exhaustive):

- `tests/test_stage_validation.py` — opportunity creation in 5 test
  bodies.
- `tests/test_sequence_engine.py` — opportunity/lead creation across
  ~12 tests.
- `tests/test_quote_revision.py` — quote creation.
- `tests/test_contract_lifecycle.py` — contract + amendment creation.
- `tests/test_campaign_roi.py` — campaign creation.

The CLAUDE.md project contract is explicit:

> Multi-tenant — every CRM row carries `tenant_id`; every router
> uses `assert_same_tenant` / `scoped_for_user`

The tests therefore violate the contract today and the test-fixture
cleanup is a prerequisite for the NOT NULL promotion — not a
side-effect of it. Promoting the constraint before the fixtures are
fixed would make CI red.

The pragmatic decision: roll back the ORM annotations + migrations,
park the work, and document the blocker.

## Unblock plan

To make Sprint 15k/15l shippable:

1. **Audit + thread tenant_id through test fixtures.** Either:
    - **Option A — fixture factory.** Add `make_customer`,
      `make_opportunity`, etc. helpers in `tests/conftest.py` that
      default `tenant_id=1`. Migrate the ~50 affected test files to
      call the factory instead of the raw constructor. Effort:
      ~1-2 days.
    - **Option B — SQLAlchemy default.** Add a column-level
      `default=` callable that reads `tenant_id` from
      `tenant_context.current_tenant()` (a `contextvars.ContextVar`
      bound in middleware + test fixture). Single-line ORM change,
      but introduces an implicit dependency on the context var being
      set. Effort: ~half day, lower test-file churn but higher
      magical-behaviour cost.
    - **Option C — hybrid.** Add the default for production paths
      (option B) but require explicit `tenant_id` in tests for
      audit visibility (option A). Effort: ~1 day; preserves
      test clarity.
2. **Re-flip the ORM annotations.** `Mapped[int | None]` →
   `Mapped[int]`; `nullable=True` → `nullable=False`.
3. **Reinstate the migrations.**
    - `20260602_phase13_tenant_not_null_cohort1.py`
    - `20260603_phase13_tenant_not_null_cohort2.py`
4. **Reinstate the floor-test allowlist additions** (the 4 cohort-1
   tables + 4 cohort-2 tables).
5. **Run `pytest -q` and confirm zero NOT NULL violations.**
6. **Tag the release.**

## What was retained

The cohort 12 migration (`20260602_phase12_tenant_did_cohort12.py`)
and the parallel ORM additions (nullable `tenant_id` on
`deal_replay_deltas`, `opportunity_text_embeddings`,
`opportunity_transformer_seq_embeddings`, `contract_amendments`)
were **kept** — they are pure defense-in-depth additions, no
constraint flip, no test impact.

The runbook `docs/runbooks/r15k-tenant-orphan-backfill.md` was
**removed** along with the migrations; if cohort 1/2 is retried,
re-create it from the version in commit history.

## Related

- Audit § F-001 — original finding (58 tables with nullable tenant_id).
- `docs/runbooks/r13-orphan-tenant-backfill.md` — proven pattern from
  the prior successful promotion (email_templates / shared_documents).
- Sprint board entry in audit § 8 — 15k = 1 week, 15l = 1 week.
