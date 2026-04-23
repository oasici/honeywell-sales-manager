#!/usr/bin/env bash
# Backend pytest — her zaman repo .venv icindeki Python ile calisir.
# Usage: ./scripts/pytest-backend.sh [pytest-args...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib-backend-venv.sh"

hsm_ensure_venv
cd "$HSM_ROOT/backend"
exec "$HSM_PY" -m pytest "$@"
