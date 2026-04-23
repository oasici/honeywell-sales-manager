#!/usr/bin/env bash
# Ortak: repo kokunu, .venv yolunu ve (gerekirse) venv kurulumunu.
# Kaynak: source "$(dirname "$0")/lib-backend-venv.sh"
# shellcheck shell=bash
_hsm_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HSM_ROOT="$(cd "$_hsm_scripts_dir/.." && pwd)"
HSM_VENV="$HSM_ROOT/.venv"
HSM_REQ="$HSM_ROOT/backend/requirements.txt"
HSM_PY="$HSM_VENV/bin/python"

hsm_pick_python() {
  local c
  for c in \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /usr/local/bin/python3.12 \
    /usr/local/bin/python3.11 \
    python3.12 \
    python3.11 \
    python3.10 \
    python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; assert sys.version_info[:2] >= (3, 10)" >/dev/null 2>&1; then
      printf '%s' "$c"
      return 0
    fi
  done
  return 1
}

# .venv yoksa olusturur ve requirements kurar.
hsm_ensure_venv() {
  if [[ -x "$HSM_PY" ]]; then
    return 0
  fi
  echo "[backend-venv] .venv yok; olusturuluyor: $HSM_VENV"
  local create_py
  create_py="$(hsm_pick_python)" || {
    echo "[backend-venv] HATA: Python 3.10+ gerekli (ornek: brew install python@3.11)." >&2
    return 1
  }
  echo "[backend-venv] Python: $create_py"
  "$create_py" -m venv "$HSM_VENV"
  "$HSM_PY" -m pip install -q --upgrade pip
  echo "[backend-venv] pip install -r backend/requirements.txt (biraz surebilir)..."
  "$HSM_PY" -m pip install -q -r "$HSM_REQ"
  echo "[backend-venv] Tamam."
}
