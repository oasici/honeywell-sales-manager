# Round-15 Sprint 15k — orphan tenant_id backfill runbook

**Audience.** On-call engineer triaging a failed Alembic migration.

**Symptom.** Migration `20260604_phase13_tenant_not_null_cohort1` (or
follow-up cohort `20260605_*`) fails with:

```
ERROR:  Sprint 15k cohort 1: cannot promote <table>.tenant_id to NOT
NULL — orphan rows remain. Run the backfill runbook before retrying.
```

The exception is raised by the guard `DO $$ ... $$` block in
`upgrade()`. The transaction has already rolled back — your DB is in
the pre-migration state.

---

## What just happened

Each cohort migration runs four steps:

1. **Defensive backfill** — fills `tenant_id` from a parent table
   (`customers` ← `users.tenant_id` via `created_by`,
   `opportunities` ← `customers.tenant_id` via `customer_id`, etc.).
2. **Single-tenant fallback** — if exactly one tenant exists in
   `tenants`, fills any remaining NULL with that tenant's id.
3. **Guard** — fails if any row still has `tenant_id IS NULL`.
4. **Promote** — `ALTER COLUMN tenant_id SET NOT NULL`.

The guard fired, which means at least one row has:

- A parent FK chain that doesn't lead to a non-NULL `tenant_id`, AND
- The deployment has 2+ tenants (so the single-tenant fallback didn't
  run).

This is a genuine orphan: a row whose creator / owner has no
`tenant_id` set, and no other parent edge provides one.

## Triage

### Step 1 — identify the offending rows

```sql
-- customers
SELECT c.id, c.name, c.created_by, u.tenant_id AS creator_tenant
FROM customers c
LEFT JOIN users u ON u.id = c.created_by
WHERE c.tenant_id IS NULL;

-- opportunities
SELECT o.id, o.title, o.customer_id, c.tenant_id AS customer_tenant,
       o.owner_id, u.tenant_id AS owner_tenant
FROM opportunities o
LEFT JOIN customers c ON c.id = o.customer_id
LEFT JOIN users u ON u.id = o.owner_id
WHERE o.tenant_id IS NULL;

-- quotes
SELECT q.id, q.quote_number, q.opportunity_id, o.tenant_id AS opp_tenant,
       q.customer_id, c.tenant_id AS customer_tenant,
       q.created_by, u.tenant_id AS creator_tenant
FROM quotes q
LEFT JOIN opportunities o ON o.id = q.opportunity_id
LEFT JOIN customers c ON c.id = q.customer_id
LEFT JOIN users u ON u.id = q.created_by
WHERE q.tenant_id IS NULL;

-- leads
SELECT l.id, l.first_name, l.last_name, l.owner_id, u.tenant_id AS owner_tenant
FROM leads l
LEFT JOIN users u ON u.id = l.owner_id
WHERE l.tenant_id IS NULL;
```

### Step 2 — fix the parent (preferred)

```sql
-- if the user is the orphan source:
UPDATE users SET tenant_id = <T> WHERE id = <user_id>;

-- if a customer is the orphan source:
UPDATE customers SET tenant_id = <T> WHERE id = <customer_id>;
```

After the parent is fixed, re-run the migration. The defensive
backfill re-cascades through the FK chain.

### Step 3 — direct fix (when the parent is intentionally tenant-less)

```sql
UPDATE <table> SET tenant_id = <T> WHERE id IN (<orphan ids>);
```

Choose `T` from `SELECT id, name FROM tenants ORDER BY id` after
confirming with the account manager.

### Step 4 — last-resort orphan archive

```sql
CREATE TABLE IF NOT EXISTS orphan_archive_<table>_20260604 AS
SELECT * FROM <table> WHERE tenant_id IS NULL;

-- Only after stakeholder sign-off:
DELETE FROM <table> WHERE tenant_id IS NULL;
```

Re-run the migration.

---

## Pre-V7 single-tenant deployments

If you're upgrading a single-tenant deployment from a pre-V7 release
(no `tenants` table populated, `users.tenant_id` is NULL across the
board), run the bootstrap script before the migration:

```bash
python backend/scripts/bootstrap_default_tenant.py
```

This creates tenant id=1 and backfills `users.tenant_id=1` for every
existing user. The cohort migration's FK-chain backfill then cascades
cleanly from `users.tenant_id` into every CRM row.

The bootstrap script is scheduled in
`.github/workflows/bootstrap-default-tenant.yml`.

---

## Why the migration fails fast

Promoting `tenant_id` to NOT NULL is one-shot — there is no way to
"partially" enforce it. Letting the migration succeed with orphan
rows would mean the next INSERT fails with a `NOT NULL constraint
violation` because the row has nothing to anchor it to.

The fail-fast guard makes the data-cleanup step visible and
intentional.

---

## Verifying after a successful upgrade

```sql
SELECT
  c.table_name,
  c.column_name,
  c.is_nullable
FROM information_schema.columns c
WHERE c.column_name = 'tenant_id'
  AND c.table_name IN ('customers', 'opportunities', 'quotes', 'leads')
ORDER BY c.table_name;
```

Expected output: all four rows show `is_nullable = NO`.

The floor test pins this assertion:

```bash
pytest backend/tests/test_round15_tenant_not_null_floor.py -q
```

Should pass with 2 tests green.

---

## Related

- `docs/runbooks/r13-orphan-tenant-backfill.md` — prior runbook for
  the email_templates / shared_documents promotion.
- `backend/alembic/versions/20260604_phase13_tenant_not_null_cohort1.py`
  — this cohort's migration.
- `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-001 — the
  originating audit finding.
- `docs/audits/2026-05-15-15kl-parking-notes.md` — parking timeline
  and unblock plan (the test-fixture sweep that landed in batches
  1-8 closed the blocker; this runbook supersedes the parked one).

---

## Appendix — Cohort 9 (Sprint 16e, 2026-05-20)

The Round-15 audit M-01 plan added eight more child tables to the
NOT NULL promotion sweep:
[`20260613_phase13_tenant_not_null_cohort9.py`](../../backend/alembic/versions/20260613_phase13_tenant_not_null_cohort9.py).

| Table | Parent FK | Notes |
|---|---|---|
| `achievements` | `user_id → users` | Closes N15-DB-2 (model NOT NULL vs DB NULLABLE) |
| `push_subscriptions` | `user_id → users` | |
| `tasks` | `owner_id → users` | `opportunity_id` is nullable; owner is the safer source |
| `campaign_members` | `campaign_id → campaigns` | Parent NOT NULL since cohort 2 |
| `webhook_deliveries` | `subscription_id → webhook_subscriptions` | Parent NOT NULL since cohort 4 |
| `revenue_schedule_entries` | `schedule_id → revenue_schedules` | |
| `contract_amendments` | `contract_id → contracts` | Parent NOT NULL since cohort 2 |
| `stakeholders` | `opportunity_id OR customer_id` | **Two-pass backfill** — opportunity first, then customer; both columns are nullable |

The fail-fast guard message changes only the sprint label; the
triage steps (1-4) above apply unchanged. The single novel SQL path
is the stakeholder two-pass backfill, which the migration already
implements — manual intervention only needed when a stakeholder row
has BOTH `opportunity_id IS NULL` AND `customer_id IS NULL` (truly
orphaned) OR when both parents have `tenant_id IS NULL` (the parent
chain itself broke).

For cohort-9-specific drift inspection:

```sql
SELECT s.id, s.opportunity_id, o.tenant_id AS opp_tenant,
       s.customer_id, c.tenant_id AS cust_tenant
FROM stakeholders s
LEFT JOIN opportunities o ON o.id = s.opportunity_id
LEFT JOIN customers c ON c.id = s.customer_id
WHERE s.tenant_id IS NULL;
```
