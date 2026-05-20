# AGENTS.md

## Cursor Cloud specific instructions

### Services overview

| Service | Port | How to run |
|---------|------|-----------|
| PostgreSQL 16 | 5432 (dev), 5434 (test) | `docker run -d --name honeywell-db -e POSTGRES_DB=honeywell_sales -e POSTGRES_USER=honeywell -e POSTGRES_PASSWORD=dev_password_2026 -p 5432:5432 postgres:16-alpine` |
| Backend (FastAPI) | 8000 | `source .venv/bin/activate && cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` |
| Frontend (Vite) | 5173 | `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173` |

### Docker daemon startup

The cloud VM requires Docker for PostgreSQL. Start it with:
```
sudo dockerd &
sudo chmod 666 /var/run/docker.sock
```
The `/etc/docker/daemon.json` should contain `{"storage-driver": "fuse-overlayfs"}` and iptables must be set to legacy mode (both are pre-configured in the VM snapshot).

### Environment file

The backend reads `.env` from CWD. A symlink at `backend/.env -> ../.env` ensures that both `alembic upgrade head` (run from `backend/`) and the uvicorn dev server pick up the same config. The root `.env` must contain at minimum:
- `DATABASE_URL=postgresql+asyncpg://honeywell:dev_password_2026@localhost:5432/honeywell_sales`
- `JWT_SECRET_KEY` (any 64-char hex string)
- `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`
- `CORS_ORIGINS` including `http://localhost:5173`

### Multi-tenant bootstrap

After first migration, run:
```
cd backend && source ../.venv/bin/activate && python -m scripts.bootstrap_default_tenant --name "Honeywell TR" --apply
```
This assigns `tenant_id=1` to the bootstrap admin user. Without it, create operations fail with NOT NULL constraint violations on `tenant_id`.

### Running tests

- **Backend (PostgreSQL):** `cd backend && source ../.venv/bin/activate && TEST_DATABASE_URL="postgresql+asyncpg://honeywell:honeywell_test_2026@localhost:5434/honeywell_sales_test" python -m pytest tests/ -v --tb=short`
- **Backend (SQLite fallback):** `TEST_DATABASE_URL=sqlite+aiosqlite:///./test.db python -m pytest tests/` (some tests may error in teardown due to SQLite limitations)
- **Frontend unit tests:** `cd frontend && npm run test`
- **Frontend lint:** `cd frontend && npm run lint` (pre-existing lint warnings exist in the codebase)
- **Frontend type check:** `cd frontend && npx tsc --noEmit`
- **Frontend build:** `cd frontend && npm run build`

### Key gotchas

- The Vite dev server proxies `/api` to `http://localhost:8000` automatically (configured in `vite.config.ts`).
- Many features (leads, AI, RAG, etc.) are behind feature flags that default to `false`. Check `FEATURE_*` env vars in `.env.example`.
- The backend uses `OAuth2PasswordRequestForm` for login — send `username` (email) + `password` as form-encoded data to `POST /api/v1/auth/login`.
- The `.venv` is at the workspace root (`/workspace/.venv`), not inside `backend/`.
- Alembic env.py falls back to SQLite if `DATABASE_URL` is empty — ensure the env var is set when running migrations against Postgres.
