#!/usr/bin/env bash
set -euo pipefail
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$BACKEND/.." && pwd)"
cd "$BACKEND"
PY="${PYTHON:-}"
if [[ -z "$PY" ]] && command -v python3.11 >/dev/null 2>&1; then PY=python3.11; fi
if [[ -z "$PY" ]]; then PY=python3; fi
if [[ -z "${DATABASE_URL:-}" && -f "$REPO/.env" ]]; then
  export DATABASE_URL="$(REPO_ROOT="$REPO" "$PY" -c "
import os, pathlib, re
p = pathlib.Path(os.environ['REPO_ROOT']) / '.env'
if not p.exists():
    raise SystemExit(0)
for line in p.read_text(errors='ignore').splitlines():
    m = re.match(r'^\\s*DATABASE_URL\\s*=\\s*(.*)$', line)
    if m:
        v = m.group(1).strip().strip('\"').strip(\"'\")
        print(v, end='')
        break
")"
fi
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///${BACKEND}/alembic_local.db}"
exec "$PY" -m alembic upgrade head
