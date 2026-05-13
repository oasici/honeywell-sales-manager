# Round-13 — Orphan-tenant backfill runbook

## Context

The Round-12 migration `20260518_phase12_tenant_columns` added a
`tenant_id` column to `email_templates` and `shared_documents` and
backfilled it from `created_by → users.tenant_id`. The column was
intentionally left nullable for one deploy cycle to absorb two
"orphan" cases the backfill could not resolve:

1. **Deleted creator** — the row's `created_by` user was hard-deleted
   before the migration ran. The backfill join (`JOIN users ON
   users.id = X.created_by`) returns no row, so `tenant_id` stays
   `NULL`.

2. **Pre-multi-tenant rows** — legacy installs created the row before
   `users.tenant_id` was added (V7). The user still exists but their
   own `tenant_id` is `NULL`. The backfill copies the source NULL.

Both cases are now invisible to tenant users (because `scoped()` adds
`column = N`, which SQL's three-valued logic rejects for NULL rows),
which is the correct *security* outcome but also means those rows are
effectively orphaned — nobody can list, edit, or delete them from the
UI.

This runbook documents how to **inspect, re-tenant, or hard-delete**
those rows before promoting the column to `NOT NULL` (deferred
migration `20260520_phase13_tenant_not_null`, not yet authored).

## Pre-flight

- Take a fresh backup. See `db-backup-restore.md`.
- Confirm you're targeting the right environment: `\conninfo` in psql,
  or `gh secret list --env <env>` for managed deploys.
- Have the admin's `tenant_id` ready for the "re-tenant" branch below.

## Step 1 — count the orphan rows

```sql
SELECT 'email_templates' AS table_name, COUNT(*) AS orphan_count
FROM email_templates WHERE tenant_id IS NULL
UNION ALL
SELECT 'shared_documents', COUNT(*)
FROM shared_documents WHERE tenant_id IS NULL;
```

Expected on a fresh install: `0` for both. Anything > 0 needs a
disposition decision before the NOT NULL migration can apply.

## Step 2 — classify orphans by source

```sql
-- email_templates: which orphans are "deleted creator" vs "tenant-NULL user"?
SELECT
    et.id,
    et.created_by,
    et.name,
    et.created_at,
    CASE
        WHEN u.id IS NULL THEN 'deleted_creator'
        WHEN u.tenant_id IS NULL THEN 'tenant_null_user'
        ELSE 'unexpected'
    END AS orphan_reason,
    u.tenant_id AS creator_tenant_id
FROM email_templates et
LEFT JOIN users u ON u.id = et.created_by
WHERE et.tenant_id IS NULL
ORDER BY et.created_at DESC;

-- shared_documents: same query with sd in place of et.
SELECT
    sd.id,
    sd.created_by,
    sd.file_name,
    sd.created_at,
    CASE
        WHEN u.id IS NULL THEN 'deleted_creator'
        WHEN u.tenant_id IS NULL THEN 'tenant_null_user'
        ELSE 'unexpected'
    END AS orphan_reason
FROM shared_documents sd
LEFT JOIN users u ON u.id = sd.created_by
WHERE sd.tenant_id IS NULL
ORDER BY sd.created_at DESC;
```

For each row, decide:

- **Re-tenant** — assign to a specific tenant_id (e.g. the admin
  tenant or the tenant the row was clearly meant for).
- **Hard-delete** — the row is genuinely abandoned (test data, demo,
  defunct creator with no business value).

## Step 3a — re-tenant a set of rows (preferred when content is valuable)

```sql
-- Example: assign three email_templates to the admin tenant (id = 1).
UPDATE email_templates
SET tenant_id = 1
WHERE id IN (42, 87, 113) AND tenant_id IS NULL;
```

```sql
-- Example: assign one shared_document to the admin tenant.
UPDATE shared_documents
SET tenant_id = 1
WHERE id = 9 AND tenant_id IS NULL;
```

Always include `AND tenant_id IS NULL` so an accidental re-run cannot
move a row that was already correctly tenanted.

## Step 3b — hard-delete orphans (preferred for test/demo data)

```sql
DELETE FROM email_templates
WHERE id IN (42, 87) AND tenant_id IS NULL;

DELETE FROM shared_documents
WHERE id IN (9) AND tenant_id IS NULL;
```

For `shared_documents`, also delete any view-tracking artifacts in
related tables (none today, but check `analytics_*` if added later).

## Step 4 — verify all orphans resolved

Re-run Step 1. Both counts must be `0` before proceeding.

## Step 5 — apply the NOT NULL migration

Once Step 4 returns `0`, the deferred Alembic revision
`20260520_phase13_tenant_not_null` (to be authored) can apply
cleanly. The revision body is sketched here so future-you doesn't
have to derive it from scratch:

```python
"""Round-13 R13-DB-2 — promote tenant_id to NOT NULL on R12 columns.

Pre-flight required: see docs/runbooks/r13-orphan-tenant-backfill.md
which asserts every email_templates / shared_documents row has a
tenant_id set. Running this migration before that runbook will fail
the ALTER COLUMN.

Revision ID: 20260520_phase13_tenant_not_null
Revises: 20260518_phase12_tenant_columns
"""

from alembic import op


revision = "20260520_phase13_tenant_not_null"
down_revision = "20260518_phase12_tenant_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # asyncpg constraint — one statement per execute() call.
    op.execute(
        "ALTER TABLE email_templates ALTER COLUMN tenant_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE shared_documents ALTER COLUMN tenant_id SET NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE email_templates ALTER COLUMN tenant_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE shared_documents ALTER COLUMN tenant_id DROP NOT NULL"
    )
```

After applying, update the ORM models in
`backend/app/models/email_template.py` and `shared_document.py` to:

```python
tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
```

The schema-drift gate (`python -m app.core.schema_check`) will then
agree with the database state and stop reporting the nullability
mismatch.

## Rollback

If the NOT NULL promotion has applied and you need to revert (e.g.
unexpected orphan row from a delayed write), run the migration
downgrade:

```bash
alembic downgrade 20260518_phase12_tenant_columns
```

This restores the column to nullable. The orphan row stays in place;
the security property (tenant users cannot see it) is unaffected.

## Why this is a runbook and not a migration

Re-tenanting orphan rows is a **business decision**, not a database
operation. There's no general rule for "where should this row go" —
each orphan needs an admin's eye on its content, creator history,
and any cross-tenant links it might have. Encoding that judgment in
an Alembic revision would either guess wrong or pick a single tenant
that doesn't actually own the data.

The deferred NOT NULL migration is sketched here so the *mechanical*
follow-up is a one-line `alembic revision` away once the human
decisions are made.
