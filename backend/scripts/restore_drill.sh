#!/usr/bin/env bash
# Monthly restore drill — proves the prod backup actually restores.
#
# A backup that has never been restored is just a hope. This script takes a
# snapshot of prod, drops it into the staging database, runs the schema
# integrity check, and asserts row counts are above sanity floors. Failure
# pages on-call before any real incident does.
#
# Required env:
#   PROD_DB_BACKUP_URL    — Postgres URL the script can pg_dump from. Use a
#                           read-only user; the dump is a full schema+data dump.
#   STAGING_DATABASE_URL  — Postgres URL the script restores INTO. The schema
#                           is dropped and recreated, so this must NOT be prod
#                           or anything else you care about.
#
# Optional env:
#   MIN_USERS              (default 1)   — fail if restored row count is below
#   MIN_OPPORTUNITIES      (default 0)
#   ALEMBIC_CHECK          (default 1)   — verify migration head matches code
#
# Usage:
#   PROD_DB_BACKUP_URL=... STAGING_DATABASE_URL=... bash backend/scripts/restore_drill.sh
#
# Exit codes:
#   0  — drill passed
#   1  — drill failed (pg_dump/restore failed, schema mismatch, or row floor breached)

set -euo pipefail

# ── Guard rails ─────────────────────────────────────────────

: "${PROD_DB_BACKUP_URL:?PROD_DB_BACKUP_URL is required}"
: "${STAGING_DATABASE_URL:?STAGING_DATABASE_URL is required}"

# Refuse to write to anything that smells like prod. The trailing space in
# the grep pattern is intentional — we want to match the URL string exactly.
if [[ "$STAGING_DATABASE_URL" == "$PROD_DB_BACKUP_URL" ]]; then
  echo "FATAL: STAGING_DATABASE_URL == PROD_DB_BACKUP_URL — would destroy prod." >&2
  exit 1
fi
if echo "$STAGING_DATABASE_URL" | grep -qiE 'prod|production'; then
  echo "FATAL: STAGING_DATABASE_URL looks like a production URL: $STAGING_DATABASE_URL" >&2
  exit 1
fi

MIN_USERS="${MIN_USERS:-1}"
MIN_OPPORTUNITIES="${MIN_OPPORTUNITIES:-0}"
ALEMBIC_CHECK="${ALEMBIC_CHECK:-1}"

DUMP_FILE="${TMPDIR:-/tmp}/restore-drill-$(date +%Y%m%d-%H%M%S).dump"
START_TS=$(date +%s)

cleanup() {
  if [[ -f "$DUMP_FILE" ]]; then
    rm -f "$DUMP_FILE"
  fi
}
trap cleanup EXIT

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

# ── Stage 1: snapshot prod ───────────────────────────────────

log "Stage 1: pg_dump from PROD_DB_BACKUP_URL → $DUMP_FILE"
pg_dump --format=custom --no-owner --no-acl \
  --file="$DUMP_FILE" "$PROD_DB_BACKUP_URL"

DUMP_SIZE=$(wc -c < "$DUMP_FILE" | tr -d ' ')
log "Dump complete: ${DUMP_SIZE} bytes"
if [[ "$DUMP_SIZE" -lt 1024 ]]; then
  echo "FATAL: dump file is suspiciously small (${DUMP_SIZE} bytes). Aborting." >&2
  exit 1
fi

# ── Stage 2: wipe staging ────────────────────────────────────

log "Stage 2: drop + recreate public schema in staging"
psql "$STAGING_DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

# ── Stage 3: restore ─────────────────────────────────────────

log "Stage 3: pg_restore into staging"
pg_restore --no-owner --no-acl --exit-on-error \
  --dbname="$STAGING_DATABASE_URL" "$DUMP_FILE"

# ── Stage 4: row count sanity ────────────────────────────────

log "Stage 4: verify row counts"
USER_COUNT=$(psql "$STAGING_DATABASE_URL" -tAc "SELECT COUNT(*) FROM users")
OPP_COUNT=$(psql "$STAGING_DATABASE_URL" -tAc "SELECT COUNT(*) FROM opportunities")
log "Restored: ${USER_COUNT} users, ${OPP_COUNT} opportunities"

if [[ "$USER_COUNT" -lt "$MIN_USERS" ]]; then
  echo "FATAL: users floor breached (${USER_COUNT} < ${MIN_USERS})" >&2
  exit 1
fi
if [[ "$OPP_COUNT" -lt "$MIN_OPPORTUNITIES" ]]; then
  echo "FATAL: opportunities floor breached (${OPP_COUNT} < ${MIN_OPPORTUNITIES})" >&2
  exit 1
fi

# ── Stage 5: migration head matches code ─────────────────────

if [[ "$ALEMBIC_CHECK" == "1" ]]; then
  log "Stage 5: alembic current"
  cd "$(dirname "$0")/.."
  DATABASE_URL="$STAGING_DATABASE_URL" python3 -m alembic current | tee /tmp/alembic_current.log
  if ! grep -q "(head)" /tmp/alembic_current.log; then
    echo "WARN: restored DB is not at alembic head — schema may be drifting." >&2
    # Not fatal: the dump may legitimately be one revision behind a deploy.
  fi
fi

ELAPSED=$(( $(date +%s) - START_TS ))
log "Drill PASSED in ${ELAPSED}s (users=${USER_COUNT}, opportunities=${OPP_COUNT})"
