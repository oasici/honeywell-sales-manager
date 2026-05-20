# Honeywell Sales Suite — Agent Instructions

See `CLAUDE.md` for stack overview, design tokens, backend conventions, and working agreements.

## Cursor Cloud specific instructions

### Services overview

| Service | How to start | Port | Notes |
|---|---|---|---|
| PostgreSQL 16 | `sudo docker start honeywell-db` (or create via Docker — see below) | 5432 | Required. Dev DB. |
| Backend (FastAPI) | `cd backend && DATABASE_URL=postgresql+asyncpg://honeywell:devpassword123@localhost:5432/honeywell_sales .venv/bin/uvicorn app.main:app --reload --port 8000` | 8000 | Health check: `GET /api/health` |
| Frontend (Vite) | `cd frontend && npm run dev` | 5173 | Proxies `/api` → `localhost:8000` |
| Test DB | `sudo docker start honeywell-db-test` | 5434 | For pytest. Password: `honeywell_test_2026` |

### Starting PostgreSQL (if container doesn't exist)

```bash
sudo docker run -d --name honeywell-db \
  -e POSTGRES_DB=honeywell_sales -e POSTGRES_USER=honeywell \
  -e POSTGRES_PASSWORD=devpassword123 -p 5432:5432 postgres:16-alpine

# Test DB (for pytest) — use fsync=off for speed:
sudo docker run -d --name honeywell-db-test \
  -e POSTGRES_DB=honeywell_sales_test -e POSTGRES_USER=honeywell \
  -e POSTGRES_PASSWORD=honeywell_test_2026 -p 5434:5432 \
  --shm-size=256m postgres:16-alpine \
  -c synchronous_commit=off -c fsync=off -c full_page_writes=off
```

### Environment variables

The backend reads `.env` from its CWD. Place `.env` in **both** `/workspace/.env` and `/workspace/backend/.env` (or export vars directly). Key dev values:

- `DATABASE_URL=postgresql+asyncpg://honeywell:devpassword123@localhost:5432/honeywell_sales`
- `JWT_SECRET_KEY` — any 64-char hex string
- `DEFAULT_ADMIN_PASSWORD` — password for `admin@honeywell.com` bootstrap account
- `CORS_ORIGINS=http://localhost,http://localhost:80,http://localhost:5173`

### Migrations

```bash
cd backend && DATABASE_URL=postgresql+asyncpg://honeywell:devpassword123@localhost:5432/honeywell_sales \
  .venv/bin/python -m alembic upgrade head
```

### Multi-tenant bootstrap

After migrations, the admin user has `tenant_id=NULL`. Run the bootstrap script to create the default tenant and backfill:

```bash
cd backend && DATABASE_URL=... .venv/bin/python -m scripts.bootstrap_default_tenant \
  --name "Honeywell TR" --apply
```

### Running tests

- **Backend**: `cd backend && .venv/bin/python -m pytest tests/ -x --tb=short -q`
  - Default: connects to PG on port 5434 (`honeywell_test_2026` password).
  - The test DB container **must** use `fsync=off` and `synchronous_commit=off` — without these, schema reset per test is extremely slow on fuse-overlayfs.
  - SQLite fallback: `TEST_DATABASE_URL=sqlite+aiosqlite:///./test.db` (some PG-specific tests may degrade).
- **Frontend unit tests**: `cd frontend && npm run test`
- **Frontend lint**: `cd frontend && npm run lint`
- **TypeScript check**: `cd frontend && npx tsc --noEmit`
- **Frontend build**: `cd frontend && npm run build`

### Gotchas

- The Docker-in-Docker environment uses `fuse-overlayfs` storage driver. PostgreSQL checkpoints are slow; always use `fsync=off` for test databases.
- `dockerd` must be started manually: `sudo dockerd &>/tmp/dockerd.log &`
- The `iptables` must be set to legacy mode for Docker networking to work: `sudo update-alternatives --set iptables /usr/sbin/iptables-legacy`
- Frontend ESLint has ~47 pre-existing warnings/errors (react-hooks/set-state-in-effect, unused vars). These are not regressions.
- The login API uses form-encoded `username` + `password` fields (OAuth2 password flow), not JSON `email` + `password`.
