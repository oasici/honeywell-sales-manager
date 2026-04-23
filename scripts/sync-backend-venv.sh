#!/usr/bin/env bash
# backend/requirements.txt dosyasini .venv ile esitler (venv yoksa olusturur).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib-backend-venv.sh"

hsm_ensure_venv
echo "[sync-backend-venv] pip install -r backend/requirements.txt"
"$HSM_PY" -m pip install --upgrade pip
"$HSM_PY" -m pip install -r "$HSM_REQ"
echo "[sync-backend-venv] Bitti."
