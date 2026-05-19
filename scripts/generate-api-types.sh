#!/usr/bin/env bash
# Generate frontend/src/lib/api-types.gen.ts from the backend's OpenAPI spec.
#
# Round-15 Sprint 15m — skeleton for the "FE types from API" migration.
# F-006 / F-009 surfaced 5+ drift sites where the SPA's hand-written
# `frontend/src/lib/types.ts` (2157 lines) lags the backend's Pydantic
# response schemas. The audit recommended `openapi-typescript` to make
# drift impossible.
#
# This script:
#   1. Boots the FastAPI app in a subprocess, hits `/openapi.json`,
#      writes it to `backend/openapi.gen.json`.
#   2. Runs `openapi-typescript` against the JSON to emit
#      `frontend/src/lib/api-types.gen.ts`.
#   3. With `--check`, compares the regenerated file against the
#      committed version and exits non-zero if they differ (CI drift
#      gate).
#
# Usage:
#   bash scripts/generate-api-types.sh           # regenerate in place
#   bash scripts/generate-api-types.sh --check   # CI mode (no edit)
#
# Prerequisites:
#   - Python venv with backend/requirements.txt installed
#   - Node 20+ with `npx` on PATH (the openapi-typescript generator is
#     fetched on-demand by npx so it doesn't have to live in
#     frontend/package.json — that avoids the v7-needs-TS-5 peer dep
#     conflict with the project's pinned TypeScript ~6.0.3).

set -euo pipefail

CHECK_MODE=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SPEC_PATH="${REPO_ROOT}/backend/openapi.gen.json"
OUT_PATH="${REPO_ROOT}/frontend/src/lib/api-types.gen.ts"

# 1. Dump OpenAPI spec from the FastAPI app.
cd "${REPO_ROOT}/backend"
python - <<'PY' > "${SPEC_PATH}"
import json
import os

# Force non-production so /openapi.json is wired and DB connections are
# stubbed where possible. The schema dump doesn't need a live DB; it just
# needs the FastAPI app object.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./_openapi_dump.db")

from app.main import app

print(json.dumps(app.openapi(), separators=(",", ":")))
PY

# 2. Run openapi-typescript against the spec.
cd "${REPO_ROOT}/frontend"

if [[ "${CHECK_MODE}" -eq 1 ]]; then
  TMP_OUT="$(mktemp)"
  trap 'rm -f "${TMP_OUT}"' EXIT
  npx --yes openapi-typescript@^7 "${SPEC_PATH}" -o "${TMP_OUT}"
  if ! diff -u "${OUT_PATH}" "${TMP_OUT}" > /dev/null; then
    echo "::error::api-types.gen.ts is out of date. Run 'npm run gen:api-types' and commit the result." >&2
    diff -u "${OUT_PATH}" "${TMP_OUT}" | head -80 >&2 || true
    exit 1
  fi
  echo "api-types.gen.ts is up to date."
else
  npx --yes openapi-typescript@^7 "${SPEC_PATH}" -o "${OUT_PATH}"
  echo "Regenerated ${OUT_PATH}"
fi
