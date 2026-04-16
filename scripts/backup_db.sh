#!/bin/bash
# Database backup script for Honeywell Sales Manager
# Usage: ./scripts/backup_db.sh [backup_dir]

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="hsm_backup_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

# Get DB credentials from docker-compose or env
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-honeywell_sales}"
DB_USER="${POSTGRES_USER:-postgres}"

echo "[$(date)] Starting backup: ${FILENAME}"

if command -v docker &> /dev/null && docker compose ps db 2>/dev/null | grep -q "running"; then
    docker compose exec -T db pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "${BACKUP_DIR}/${FILENAME}"
else
    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "${BACKUP_DIR}/${FILENAME}"
fi

echo "[$(date)] Backup complete: ${BACKUP_DIR}/${FILENAME} ($(du -h "${BACKUP_DIR}/${FILENAME}" | cut -f1))"

# Rotate old backups
find "$BACKUP_DIR" -name "hsm_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Cleaned backups older than ${RETENTION_DAYS} days"
