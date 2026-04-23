#!/usr/bin/env bash
# 1) Model/DB sem denetimi  2) Fark varsa veya her zaman idempotent: alembic upgrade head  3) Tekrar denetim
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib-backend-venv.sh"
hsm_ensure_venv

_saved_db_url="${DATABASE_URL:-}"
if [[ -f "$HSM_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$HSM_ROOT/.env" || true
  set +a
fi
if [[ -n "$_saved_db_url" ]]; then
  export DATABASE_URL="$_saved_db_url"
fi
if [[ -n "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="${DATABASE_URL/@db:/@127.0.0.1:}"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[db-ensure-aligned] DATABASE_URL gerekli." >&2
  exit 2
fi

cd "$HSM_ROOT/backend"

echo "[db-ensure-aligned] (1/3) Sem denetimi..."
set +e
bash "$HSM_ROOT/scripts/db-schema-audit.sh"
_audit1=$?
set -e

echo "[db-ensure-aligned] (2/3) alembic upgrade head..."
"$HSM_PY" -m alembic upgrade head

echo "[db-ensure-aligned] (3/3) Sem denetimi tekrar..."
bash "$HSM_ROOT/scripts/db-schema-audit.sh"
_audit2=$?

if [[ "$_audit2" -ne 0 ]]; then
  echo "[db-ensure-aligned] HATA: Migrasyon sonrasi hala sem/model uyumsuz." >&2
  exit "$_audit2"
fi

echo "[db-ensure-aligned] Tamam (ilk denetim kodu: ${_audit1})."
