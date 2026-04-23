#!/usr/bin/env bash
# Model vs Postgres sema denetimi. DATABASE_URL: .env veya ortam (db-upgrade ile ayni mantik).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib-backend-venv.sh"
hsm_ensure_venv

_saved_db_url="${DATABASE_URL:-}"
if [[ -f "$HSM_ROOT/.env" ]]; then
  set -a
  if ! . "$HSM_ROOT/.env"; then
    echo "[db-schema-audit] UYARI: .env source edilemedi." >&2
  fi
  set +a
fi
if [[ -n "$_saved_db_url" ]]; then
  export DATABASE_URL="$_saved_db_url"
fi
if [[ -n "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="${DATABASE_URL/@db:/@127.0.0.1:}"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[db-schema-audit] DATABASE_URL gerekli (.env veya export)." >&2
  exit 2
fi

exec "$HSM_PY" "$HSM_ROOT/scripts/db_schema_audit.py"
