# Honeywell Sales Suite — Claude Code Project Memory

This file is loaded into Claude's context on every prompt within this project.
Keep it terse, factual, and current. Edit when conventions change.

---

## Stack

- **Frontend** — React 18 + TypeScript + Tailwind CSS v4 (CSS-first `@theme` config in `frontend/src/index.css`, no `tailwind.config.js`)
- **Component library** — hand-rolled primitives in `frontend/src/components/ui/` (Button, Card, Badge, Input, Select, Modal, DataTable, etc.). **No shadcn/ui, no Radix, no Material.** When you need a primitive, extend the existing one rather than introducing a dependency.
- **State** — TanStack Query for server state, Zustand for auth, URL params for filters
- **Backend** — FastAPI + SQLAlchemy 2.0 async + asyncpg (PostgreSQL) + Alembic
- **Auth** — cookie-first (httpOnly access_token + readable csrf_token), Bearer fallback for legacy clients
- **Multi-tenant** — every CRM row carries `tenant_id`; every router uses `assert_same_tenant` / `scoped_for_user`
- **Deploy** — Render auto-deploys off `deploy/render-sandbox`

---

## Design Direction — Linear / Stripe aesthetic

This is a **professional CRM for sales teams**, not a consumer product. Bias toward:
- **Calm over loud** — single accent color, dense information without chrome
- **Editorial typography** — Inter with negative letter-spacing on headings, hierarchy through weight + size, not color
- **Borders over shadows** — 1px `--border` defines surfaces; shadows are elevation cues only
- **Restraint with motion** — 150-180ms transitions, no decorative animation, respect `prefers-reduced-motion`

### Tokens (defined in `frontend/src/index.css`)

| Concept | Token | Use when |
|---|---|---|
| Brand accent | `--color-honeywell-red` (#E53935) | Primary CTAs, focused inputs, danger affirmation. **Max 1-2 per viewport.** |
| Brand variants | `--color-honeywell-dark`, `--color-honeywell-light` | Hover state on primary, badge backgrounds |
| Neutral surface | `--surface`, `--surface-secondary`, `--surface-elevated` | Page bg, cards, modals — auto light/dark |
| Text | `--text-primary` / `--text-secondary` / `--text-muted` / `--text-inverse` | Use semantic tokens, not raw slate-* utilities, for body copy |
| Border | `--border`, `--border-light`, `--border-focus` | Card outlines, dividers, focus state |
| Semantic | `--success` / `--warning` / `--danger` / `--info` (+ `-bg` variants) | Badges, toasts, status indicators |
| Radius | `--radius-sm` (6px) / `-md` (8) / `-lg` (12) / `-xl` (16) / `-2xl` (20) / `-full` | Inputs/buttons → md, cards → xl, pills → full |
| Shadow | `--shadow-xs` … `--shadow-xl` | xs default, sm on hover, md+ for modals/popovers only |
| Focus ring | `--focus-ring` (red @ 16% alpha) | All interactive elements; never `outline: none` without replacement |
| Font | `--font-sans` (Inter→Geist) / `--font-mono` (JetBrains Mono) | Body copy + numerics |

### Typography utilities (in `index.css`)

`text-heading-1` (32/40/700 -2%) · `text-heading-2` (24/32/700 -1.5%) · `text-heading-3` (18/28/600 -1%) · `text-heading-4` (16/24/600) · `text-body` (14/22/400) · `text-body-strong` (14/22/500) · `text-caption` (12/18/500 muted) · `text-overline` (11/600 +6% uppercase muted)

**Use these classes for hierarchy. Do not reinvent with raw `text-2xl font-bold tracking-tight` chains.**

### Component primitives — the canonical list

| Component | Purpose | When to extend vs. introduce |
|---|---|---|
| `Button` | 5 variants (primary/secondary/tertiary/danger/ghost) × 3 sizes (sm/md/lg) | Always extend. New variant? Add to `variantClasses` in `Button.tsx`. |
| `Card` | Title + description + action slot, optional `interactive`/`padding="none"` | Always extend. Use `padding="none"` for table-flush layouts. |
| `Badge`, `Input`, `Select`, `Modal`, `ConfirmDialog`, `EmptyState`, `Skeleton`, `LoadingSpinner`, `DataTable`, `PageHeader`, `BulkActionBar` | Hand-rolled, themed | Same — extend in place. |

If a primitive feels missing, propose adding it to `components/ui/` and exporting from `components/ui/index.ts`. Don't reach for an external library.

### Banned patterns

- Generic AI-template look: cookie-cutter purple-blue gradient hero, Inter+default everything, uniform shadow-md cards, "rounded-2xl bg-white p-6 shadow" stacks
- Animating layout-bound properties (width/height/margin/padding/font-size/top/left). Animate `transform`, `opacity`, `clip-path` only.
- `outline: none` without a replacement focus indicator
- Hardcoded hex/rgb in JSX. Use the CSS custom properties or Tailwind tokens that map to them.
- Tailwind v3 `tailwind.config.js` syntax. We're on v4 CSS-first `@theme`.
- Reaching for shadcn / Radix / Material — we already have primitives; extend them.
- Tailwind `!` important prefix in legacy form (`!bg-green-600`) — use canonical v4 form (`bg-green-600!`) per round-4 v1.9.13.

### Required qualities (every meaningful surface)

1. Hierarchy via scale + weight contrast, not via `text-honeywell-red` everywhere
2. Intentional spacing rhythm — multiples of 4px (Tailwind's default scale)
3. Explicit hover/focus/active/disabled states for every interactive element
4. Dark mode parity — test both themes
5. Mobile responsiveness with `hidden sm:table-cell` patterns for less-important columns

---

## Backend conventions

### Tenant scoping (CRITICAL)

Every router that loads a single row by ID must call:
```python
from app.services.tenant_context import assert_same_tenant
record = (await db.execute(select(Model).where(Model.id == id_))).scalar_one_or_none()
if record is None: raise NotFoundException("Not found")
assert_same_tenant(record, current_user, exception_cls=NotFoundException)
```

Every list endpoint must use `scoped_for_user(stmt, current_user, column=Model.tenant_id)`.

Cross-tenant access maps to **404, not 403** — never leak existence of foreign-tenant rows.

### Field-level permission masking

Serializers for `customer / quote / opportunity / lead / email / contract / invoice / subscription / campaign` MUST end with:
```python
from app.services.field_permission_service import apply_request_perms
return apply_request_perms(data, "<entity_type>")
```

This applies admin-configured masking rules. Skipping it makes the rules dead code.

### Pagination envelope

Canonical shape across all list endpoints:
```python
return {
    "items": [...],
    "total": total,
    "page": page,
    "page_size": page_size,
    "pages": math.ceil(total / page_size) if total > 0 else 0,
}
```

Default `page_size=50`, max 100-200. Don't invent `{breaches: [], count: N}`-style envelopes.

### Migrations

- Idempotent. Use `IF NOT EXISTS` / `IF EXISTS` everywhere — round-4 bootstrap consolidation expects it.
- Backfill new columns from a sensible source (e.g. `tenant_id` from `users.tenant_id` of `created_by`). Document the choice in the migration docstring.
- Run `python backend/scripts/regenerate_bootstrap_migration.py` after adding a new model so the bootstrap snapshot stays current (R5-DB-1).

### Pydantic schemas

- Pinned to **2.13.x** (post-round-5). Use `model_config = {"from_attributes": True}` for response schemas.
- Round-trip `tenant_id` (and other multi-tenant boundary fields) explicitly — `getattr(obj, "tenant_id", None)` is fine for legacy compat.
- Use `EmailStr` at boundaries that accept emails (Lead/Customer/User/WebLead create paths).

### Testing

- pytest + pytest-asyncio + httpx AsyncClient, fixtures in `backend/tests/conftest.py`
- Test DB defaults to PostgreSQL on `localhost:5434` (docker-compose db-test); `TEST_DATABASE_URL=sqlite+aiosqlite:///./test.db` for offline.
- `_reset_rate_limit_buckets` autouse fixture clears module-level deques between tests
- 80%+ coverage on new code (round-5 sustained 806 passing tests on the composed deploy state)

---

## Frontend conventions

### Tailwind v4

- All design tokens live in `index.css` `@theme { ... }` block. Never edit `tailwind.config.js` (it doesn't exist).
- Dark mode is class-based via `@custom-variant dark (&:where(.dark, .dark *))`.
- Prefer custom property tokens (`var(--surface)`) for non-Tailwind contexts (CSS modules, dynamic styles).

### TanStack Query

- `staleTime: 30_000` global default (in `main.tsx`)
- `queryClient.clear()` is wired into `authStore.logout()` AND the 401 redirect path (R5-CACHE-1) — don't bypass it
- Mutation invalidation goes through `lib/cacheInvalidation.ts` helpers, not ad-hoc `invalidateQueries({queryKey: [...]})` calls
- Cross-feature invalidations (e.g. closing a deal invalidates kanban + dashboard + reports) belong in the helper, not in the component

### Forms

- React Hook Form + Zod for validation when the form has >3 fields
- Schema in the same file as the form, exported as `<FeatureName>FormSchema` so callers can re-use it
- Submit handlers should `mutateAsync` + invalidate via cacheInvalidation helper, not `setState` + manual refetch

### Feature-flag gating

The SPA exposes flags via `useFeatureFlags()`. Wrap routes with `<FeatureFlagGate flag="FEATURE_X">`. Sidebar items also gate on `isEnabled('FEATURE_X')`. Backend must have a matching `_require_x()` dependency — never ship a frontend-only gate (round-5 R5-FLAG-15/16/17).

### TypeScript

- Strict mode. `tsc --noEmit --pretty false` must pass before commit.
- Explicit types on exported functions/components, infer for locals.
- Optional fields use `field?: T` (not `field: T | undefined`) — Pydantic-generated optional fields land as `?` in `frontend/src/lib/types.ts`.
- Round-trip `tenant_id`, `manager_id`, `password_change_required` in TS even when the SPA doesn't render them (round-5 R5-TS-4/17..20).

---

## Working agreements

- **Round-5 audit** at `docs/audits/2026-05-05-cross-layer-audit-round5.md` — 96 findings, all closed in v1.10.0..v1.10.11
- **Deploy branch**: `deploy/render-sandbox` (auto-deploys to Render Free tier)
- **Versioning**: release-please bot opens a PR per release; tag format `v1.X.Y`
- **CI gates** that must stay green: frontend-security, backend-migrations, backend-security, frontend-build, backend-test, frontend-e2e-smoke, docker-build
- **Schema drift gate**: `python -m app.core.schema_check` must report `clean` on every push (R5-DB-8)
- **PR review**: Gemini reviews automatically; address `medium`+ findings before merge

When in doubt, search the codebase for the existing pattern. This project values consistency over novelty.
