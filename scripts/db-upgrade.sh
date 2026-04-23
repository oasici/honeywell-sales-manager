#!/usr/bin/env bash
# Alembic: mevcut revizyonu gosterir, ardindan upgrade head (prod ile ayni migrasyon zinciri).
# DATABASE_URL: .env (repo kok) veya ortam degiskeni. Docker .env icinde @db: ise hosttan calisirken 127.0.0.1 yapilir.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib-backend-venv.sh"
hsm_ensure_venv

# Ust shell'den gelen DATABASE_URL (CI / manuel) .env'den sonra da korunur.
_saved_db_url="${DATABASE_URL:-}"
if [[ -f "$HSM_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  if ! . "$HSM_ROOT/.env"; then
    echo "[db-upgrade] UYARI: .env source edilemedi; sadece ortam degiskenleri kullanilacak." >&2
  fi
  set +a
fi
if [[ -n "$_saved_db_url" ]]; then
  export DATABASE_URL="$_saved_db_url"
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="${DATABASE_URL/@db:/@127.0.0.1:}"
fi

cd "$HSM_ROOT/backend"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[db-upgrade] DATABASE_URL tanimli degil." >&2
  echo "  Repo kokunde .env icine DATABASE_URL ekleyin veya:" >&2
  echo "  export DATABASE_URL='postgresql+asyncpg://USER:PASS@127.0.0.1:5432/honeywell_sales'" >&2
  exit 1
fi

echo "[db-upgrade] head (beklenen):"
"$HSM_PY" -m alembic heads
echo "[db-upgrade] simdiki revizyon:"
"$HSM_PY" -m alembic current
echo "[db-upgrade] upgrade head calistiriliyor..."
"$HSM_PY" -m alembic upgrade head
echo "[db-upgrade] guncel revizyon:"
"$HSM_PY" -m alembic current
echo "[db-upgrade] Tamam."
