#!/usr/bin/env bash
#
# Bring up the local Postgres stack and bootstrap the dev schema.
#
# One-liner after cloning:
#   cd backend && bash scripts/dev_setup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

cd "$REPO_ROOT"

echo "==> Starting Postgres / Redis / Qdrant via docker-compose.dev.yml"
docker compose -f docker-compose.dev.yml up -d db redis qdrant

echo "==> Waiting for Postgres to accept connections"
for _ in {1..30}; do
  if docker compose -f docker-compose.dev.yml exec -T db pg_isready -U honeywell > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

cd "$BACKEND_DIR"

if [[ ! -d "venv" ]]; then
  echo "==> Creating backend venv"
  python3.11 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

python -m pip install --upgrade pip wheel >/dev/null
pip install -r requirements.txt >/dev/null

export DATABASE_URL="postgresql+asyncpg://honeywell:honeywell_dev_2026@localhost:5432/honeywell_sales_dev"
export REDIS_URL="redis://localhost:6379/0"
export ENV="development"
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')}"

echo "==> Running scripts/verify_migrations"
python -m scripts.verify_migrations

echo "==> Bootstrapping schema (Base.metadata.create_all + alembic stamp head)"
python -c "
import asyncio
from app.core.database import engine, Base
from app.models import *  # noqa: F401,F403

async def _bootstrap():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(_bootstrap())
print('  schema created')
"

# Stamp to head so subsequent alembic commands know the DB is migrated.
alembic stamp head

echo "==> Ready. DATABASE_URL:"
echo "    $DATABASE_URL"
echo ""
echo "Activate venv + export env vars then run:"
echo "  uvicorn app.main:app --reload --port 8000"
