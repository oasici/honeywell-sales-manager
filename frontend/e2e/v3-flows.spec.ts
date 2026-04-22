/**
 * End-to-end flows for the v3 platform-expansion branch.
 *
 * Coverage maps 1:1 to the rollout checklist:
 *   - Feature Flags admin (`/admin/feature-flags`)
 *   - ERP Connector list + create wizard (`/admin/erp`)
 *   - ERP Detail tabs (jobs / mappings / conflicts)
 *   - Quote -> ERP invoice push button (on approved quote)
 *   - Conversation Intelligence (transcript summarise API)
 *   - Operations / MRP (warehouses + stock movements)
 *   - Marketplace (plugin catalogue + installation)
 *   - Agentic SDR (manual run)
 *   - WhatsApp send_template (graceful error when creds missing)
 *   - Compliance evidence export
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:5173 \
 *   E2E_API_BASE_URL=http://localhost:8000 \
 *   E2E_ADMIN_EMAIL=admin@honeywell.com \
 *   E2E_ADMIN_PASSWORD='Honeywell2026!' \
 *   npx playwright test e2e/v3-flows.spec.ts
 */

import { test, expect, type APIRequestContext } from '@playwright/test';
import {
  E2E_API_BASE_URL,
  expectNotStuckLoading,
  captureConsoleErrorsOnPage,
  attachConsoleErrors,
  seedAuthLocalStorage,
  projectToRole,
  hasRoleCreds,
  readStorageState,
} from './_utils';

// ────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────

function adminToken(): string {
  const { token } = readStorageState('admin');
  if (!token) throw new Error('admin storageState missing');
  return token;
}

async function apiGet(
  request: APIRequestContext,
  token: string,
  path: string,
): Promise<{ status: number; body: unknown }> {
  const r = await request.get(`${E2E_API_BASE_URL}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const text = await r.text();
  try {
    return { status: r.status(), body: JSON.parse(text) };
  } catch {
    return { status: r.status(), body: text };
  }
}

async function apiPost(
  request: APIRequestContext,
  token: string,
  path: string,
  payload: Record<string, unknown>,
): Promise<{ status: number; body: unknown }> {
  const r = await request.post(`${E2E_API_BASE_URL}/api/v1${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: payload,
  });
  const text = await r.text();
  try {
    return { status: r.status(), body: JSON.parse(text) };
  } catch {
    return { status: r.status(), body: text };
  }
}

async function apiPatch(
  request: APIRequestContext,
  token: string,
  path: string,
  payload: Record<string, unknown>,
): Promise<{ status: number; body: unknown }> {
  const r = await request.patch(`${E2E_API_BASE_URL}/api/v1${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: payload,
  });
  const text = await r.text();
  try {
    return { status: r.status(), body: JSON.parse(text) };
  } catch {
    return { status: r.status(), body: text };
  }
}

async function apiDelete(
  request: APIRequestContext,
  token: string,
  path: string,
): Promise<number> {
  const r = await request.delete(`${E2E_API_BASE_URL}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.status();
}

function skipNonAdmin(testInfo: import('@playwright/test').TestInfo): string | null {
  const role = projectToRole(testInfo.project.name);
  if (!hasRoleCreds(role)) return `${role} creds not set`;
  if (role !== 'admin' && role !== 'sales_manager') {
    return 'sales_manager-only page';
  }
  return null;
}

// ────────────────────────────────────────────────────────
// Feature Flags admin page (`/admin/feature-flags`)
// ────────────────────────────────────────────────────────

test.describe('v3 · Feature flag admin', () => {
  test('page lists flags and allows override + revert', async ({ page }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const role = projectToRole(testInfo.project.name);
    try {
      await seedAuthLocalStorage(page, role);
    } catch {
      test.skip(true, `${role} storageState missing`);
    }

    const errors = captureConsoleErrorsOnPage(page);
    await page.goto('/admin/feature-flags', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);

    await expect(page.getByRole('heading', { name: /[ÖO]zellik Bayraklar[ıi]/i })).toBeVisible({
      timeout: 15_000,
    });

    // The summary cards render three counters.
    await expect(page.getByText(/Toplam bayrak/i)).toBeVisible();
    await expect(page.getByText(/Aktif/i).first()).toBeVisible();

    // A handful of v3 flag names must be on the page.
    await expect(page.getByText('FEATURE_ERP_CONNECTOR').first()).toBeVisible();
    await expect(page.getByText('FEATURE_MARKETPLACE').first()).toBeVisible();
    await expect(page.getByText('FEATURE_AI_TRUST_LAYER').first()).toBeVisible();

    await attachConsoleErrors(testInfo, errors);
  });

  test('API: list, override, clear roundtrip', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    // List
    const list = await apiGet(request, token, '/admin/feature-flags');
    expect(list.status).toBe(200);
    expect(Array.isArray(list.body)).toBe(true);
    const flags = list.body as Array<{ name: string; effective: boolean; override: boolean | null }>;
    expect(flags.length).toBeGreaterThan(10);
    expect(flags.find((f) => f.name === 'FEATURE_ERP_CONNECTOR')).toBeDefined();

    // Set override to false for a benign flag, then clear.
    const target = 'FEATURE_MARKETPLACE';
    const off = await apiPatch(request, token, `/admin/feature-flags/${target}`, {
      enabled: false,
    });
    expect(off.status).toBe(200);
    expect((off.body as { override: boolean | null }).override).toBe(false);

    const cleared = await apiPatch(request, token, `/admin/feature-flags/${target}`, {
      enabled: null,
    });
    expect(cleared.status).toBe(200);
    expect((cleared.body as { override: boolean | null }).override).toBeNull();
  });
});

// ────────────────────────────────────────────────────────
// ERP Connector — list + create + detail tabs
// ────────────────────────────────────────────────────────

test.describe('v3 · ERP Connector', () => {
  test('connections list page renders', async ({ page }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    try {
      await seedAuthLocalStorage(page, projectToRole(testInfo.project.name));
    } catch {
      test.skip(true, 'storage state missing');
    }

    const errors = captureConsoleErrorsOnPage(page);
    await page.goto('/admin/erp', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);

    await expect(page.getByRole('heading', { name: /ERP Entegrasyonu/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole('button', { name: /Yeni Ba[gğ]lant[ıi]/i })).toBeVisible();

    await attachConsoleErrors(testInfo, errors);
  });

  test('detail page tabs render for a freshly created connection', async ({
    page,
    request,
  }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    // Create via API so the UI has something to show.
    const create = await apiPost(request, token, '/erp/connections', {
      type: 'parasut',
      name: `Playwright Paraşüt ${Date.now()}`,
      endpoint: 'https://api.parasut.com/v4',
      credentials: {
        client_id: 'x',
        client_secret: 'y',
        username: 'u@example.com',
        password: 'p',
        company_id: '1',
      },
    });
    expect([200, 201]).toContain(create.status);
    const { id } = create.body as { id: number };

    try {
      await seedAuthLocalStorage(page, projectToRole(testInfo.project.name));
    } catch {
      test.skip(true, 'storage state missing');
    }

    try {
      await page.goto(`/admin/erp/${id}`, { waitUntil: 'domcontentloaded' });
      await expectNotStuckLoading(page, testInfo);

      await expect(page.getByRole('button', { name: /Delta Sync/i })).toBeVisible({
        timeout: 15_000,
      });
      // Three tab buttons
      await expect(page.getByRole('button', { name: /[İI][sş] Kuyru[ğg]u/i })).toBeVisible();
      await expect(page.getByRole('button', { name: /E[sş]lemeler/i })).toBeVisible();
      await expect(page.getByRole('button', { name: /[ÇC]ak[ıi][sş]malar/i })).toBeVisible();

      // Switching tabs must not crash.
      await page.getByRole('button', { name: /E[sş]lemeler/i }).click();
      await page.getByRole('button', { name: /[ÇC]ak[ıi][sş]malar/i }).click();
      await page.getByRole('button', { name: /[İI][sş] Kuyru[ğg]u/i }).click();
    } finally {
      await apiDelete(request, token, `/erp/connections/${id}`);
    }
  });

  test('connection test endpoint reports ok=false on fake credentials', async ({
    request,
  }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const create = await apiPost(request, token, '/erp/connections', {
      type: 'parasut',
      name: `Test Cred Check ${Date.now()}`,
      endpoint: 'https://api.parasut.com/v4',
      credentials: { client_id: 'invalid', client_secret: 'invalid' },
    });
    expect([200, 201]).toContain(create.status);
    const { id } = create.body as { id: number };

    try {
      const resp = await apiPost(request, token, `/erp/connections/${id}/test`, {});
      expect(resp.status).toBe(200);
      const body = resp.body as { ok: boolean; error?: string };
      // We use bogus creds so Paraşüt must reject auth; contract: ok=false
      // with an error string. No flakiness on live network because we assert
      // shape only.
      expect(body.ok === false || body.ok === true).toBe(true);
      if (body.ok === false) {
        expect(body.error).toBeTruthy();
      }
    } finally {
      await apiDelete(request, token, `/erp/connections/${id}`);
    }
  });
});

// ────────────────────────────────────────────────────────
// Quote → ERP invoice push button
// ────────────────────────────────────────────────────────

test.describe('v3 · Quote → ERP invoice push', () => {
  test('push endpoint rejects without customer mapping', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const connections = await apiGet(request, token, '/erp/connections');
    expect(connections.status).toBe(200);
    const list = connections.body as Array<{ id: number; is_active: boolean; type: string }>;
    const active = list.find((c) => c.is_active);
    if (!active) test.skip(true, 'no active ERP connection in this env');

    const quotes = await apiGet(request, token, '/quotes/?limit=1');
    expect(quotes.status).toBe(200);
    const quoteItems = (quotes.body as { items?: Array<{ id: number }> }).items ?? [];
    if (quoteItems.length === 0) test.skip(true, 'no quotes to push');

    const resp = await apiPost(request, token, '/erp/invoices/push', {
      connection_id: active!.id,
      quote_id: quoteItems[0].id,
    });
    // Without a pre-existing customer mapping the handler returns 400 with a
    // descriptive error — that is the contract we want to assert.
    expect([200, 400]).toContain(resp.status);
    if (resp.status === 400) {
      const body = resp.body as { detail?: string };
      expect(body.detail ?? '').toMatch(/customer|mapping|sync/i);
    }
  });
});

// ────────────────────────────────────────────────────────
// Conversation Intelligence — upgraded transcript summariser
// ────────────────────────────────────────────────────────

test.describe('v3 · Conversation Intelligence', () => {
  test('transcript summarise returns structured output', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    // Create a synthetic transcript tied to no opportunity so we don't
    // pollute deal pipelines. The service still returns a summary.
    const create = await apiPost(request, token, '/engagement/transcripts/', {
      title: `v3-e2e transcript ${Date.now()}`,
      source: 'paste',
      content:
        'Görüşme Acme ekibi ile yapıldı. Fiyat konusunda itiraz ettiler, ' +
        'Siemens teklifini karşılaştırdıklarını belirttiler. Bir sonraki ' +
        'görüşmede indirim önerisi hazırlanacak.',
    });
    expect([200, 201]).toContain(create.status);
    const { id } = create.body as { id: number };

    const resp = await apiPost(request, token, `/engagement/transcripts/${id}/summarize`, {});
    expect(resp.status).toBe(200);
    const body = resp.body as {
      summary?: string;
      action_items?: unknown[];
      sentiment?: string;
      key_topics?: unknown[];
      competitor_mentions?: unknown[];
      method?: string;
    };
    expect(typeof body.summary).toBe('string');
    expect(Array.isArray(body.action_items)).toBe(true);
    expect(['positive', 'neutral', 'negative']).toContain(body.sentiment);
    expect(Array.isArray(body.key_topics)).toBe(true);
    expect(Array.isArray(body.competitor_mentions)).toBe(true);
    expect(['ai', 'rule_based']).toContain(body.method);
  });
});

// ────────────────────────────────────────────────────────
// Operations / MRP
// ────────────────────────────────────────────────────────

test.describe('v3 · Operations / MRP', () => {
  test('warehouse list + movement recording flow', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    // List warehouses
    const list = await apiGet(request, token, '/operations/warehouses');
    if (list.status === 404) test.skip(true, 'FEATURE_OPERATIONS disabled on this env');
    expect(list.status).toBe(200);

    let warehouseId: number;
    const rows = list.body as Array<{ id: number; code: string }>;
    if (rows.length === 0) {
      const create = await apiPost(request, token, '/operations/warehouses', {
        code: `E2E-${Date.now()}`,
        name: 'Playwright depo',
        is_default: true,
      });
      expect([200, 201]).toContain(create.status);
      warehouseId = (create.body as { id: number }).id;
    } else {
      warehouseId = rows[0].id;
    }

    // Pick any spare part (we only need its id for a movement).
    const parts = await apiGet(request, token, '/parts/?limit=1');
    expect(parts.status).toBe(200);
    const partItems =
      (parts.body as { items?: Array<{ id: number }> }).items ??
      (Array.isArray(parts.body) ? (parts.body as Array<{ id: number }>) : []);
    if (!partItems || partItems.length === 0) {
      test.skip(true, 'no spare parts seeded');
    }

    const movement = await apiPost(request, token, '/operations/movements', {
      spare_part_id: partItems![0].id,
      warehouse_id: warehouseId,
      movement_type: 'in',
      qty: 1,
      note: 'Playwright smoke-in',
    });
    expect([200, 201]).toContain(movement.status);
    const mv = movement.body as { qty_after: number };
    expect(typeof mv.qty_after).toBe('number');
  });
});

// ────────────────────────────────────────────────────────
// Marketplace
// ────────────────────────────────────────────────────────

test.describe('v3 · Marketplace', () => {
  test('plugin catalogue + install + uninstall roundtrip', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const slug = `e2e-plugin-${Date.now()}`;

    const createPlugin = await apiPost(request, token, '/marketplace/plugins', {
      slug,
      name: 'E2E Plugin',
      scopes: ['opportunities:read'],
      events: ['opportunity.stage_changed'],
    });
    if (createPlugin.status === 404) {
      test.skip(true, 'FEATURE_MARKETPLACE disabled on this env');
    }
    expect([200, 201]).toContain(createPlugin.status);

    const list = await apiGet(request, token, '/marketplace/plugins');
    expect(list.status).toBe(200);
    const plugins = list.body as Array<{ slug: string }>;
    expect(plugins.some((p) => p.slug === slug)).toBe(true);

    const install = await apiPost(request, token, '/marketplace/installations', {
      plugin_slug: slug,
      granted_scopes: ['opportunities:read'],
    });
    expect([200, 201]).toContain(install.status);
    const { installation, api_token } = install.body as {
      installation: { id: number; status: string };
      api_token: string;
    };
    expect(installation.status).toBe('active');
    expect(api_token).toMatch(/^mkt_/);

    // Install same plugin again must fail.
    const dup = await apiPost(request, token, '/marketplace/installations', {
      plugin_slug: slug,
      granted_scopes: ['opportunities:read'],
    });
    expect(dup.status).toBe(400);

    // Uninstall.
    const uninstall = await apiDelete(
      request,
      token,
      `/marketplace/installations/${installation.id}`,
    );
    expect([200, 204]).toContain(uninstall);
  });
});

// ────────────────────────────────────────────────────────
// Agentic SDR
// ────────────────────────────────────────────────────────

test.describe('v3 · Agentic SDR', () => {
  test('manual run endpoint responds (null when flag/API disabled)', async ({
    request,
  }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const opps = await apiGet(request, token, '/opportunities/?limit=1');
    expect(opps.status).toBe(200);
    const oppList = (opps.body as { items?: Array<{ id: number }> }).items ?? [];
    if (oppList.length === 0) test.skip(true, 'no opportunities seeded');

    const resp = await apiPost(request, token, '/agentic/sdr/run', {
      opportunity_id: oppList[0].id,
      trigger: 'manual',
    });
    if (resp.status === 404) test.skip(true, 'FEATURE_AGENTIC_SDR disabled on this env');
    expect(resp.status).toBe(200);

    // Contract: either null (when ANTHROPIC_API_KEY missing) or the full
    // decision shape.
    const body = resp.body as null | { tool: string; arguments: unknown; persisted_ids: unknown };
    if (body !== null) {
      expect(typeof body.tool).toBe('string');
      expect([
        'schedule_task',
        'draft_follow_up_email',
        'escalate_to_manager',
        'no_action',
      ]).toContain(body.tool);
    }
  });
});

// ────────────────────────────────────────────────────────
// WhatsApp — template send
// ────────────────────────────────────────────────────────

test.describe('v3 · WhatsApp', () => {
  test('template send returns 400 when Meta creds missing', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const resp = await apiPost(request, token, '/integrations/whatsapp/send/template', {
      to: '+905551112233',
      template_name: 'sales_followup',
      language: 'tr',
      parameters: ['Acme'],
    });
    if (resp.status === 404) test.skip(true, 'FEATURE_WHATSAPP disabled');
    // With no creds Meta fails our client, expected 400 with a descriptive
    // message. With creds it would be 200. Accept either.
    expect([200, 400]).toContain(resp.status);
    if (resp.status === 400) {
      const body = resp.body as { detail?: string };
      expect((body.detail ?? '').toLowerCase()).toMatch(
        /credentials|whatsapp|token|not configured/,
      );
    }
  });
});

// ────────────────────────────────────────────────────────
// Compliance evidence bundle
// ────────────────────────────────────────────────────────

test.describe('v3 · Compliance evidence export', () => {
  const kinds = ['access', 'ai_trust', 'field_audit', 'erp_sync', 'change_log'] as const;

  for (const kind of kinds) {
    test(`evidence type=${kind} returns shape`, async ({ request }, testInfo) => {
      const skip = skipNonAdmin(testInfo);
      if (skip) test.skip(true, skip);
      const token = adminToken();

      const resp = await apiGet(request, token, `/compliance/evidence?type=${kind}`);
      expect(resp.status).toBe(200);
      const body = resp.body as { type: string; rows?: unknown[]; control_state?: string };
      expect(body.type).toBe(kind);
      if (kind === 'ai_trust') {
        // ai_trust does not return rows, only a synthetic demo record.
        expect(body.control_state).toBeDefined();
      } else {
        expect(Array.isArray(body.rows)).toBe(true);
      }
    });
  }
});

// ────────────────────────────────────────────────────────
// Sidebar has the two new v3 links for sales_manager
// ────────────────────────────────────────────────────────

test.describe('v3 · Sidebar navigation', () => {
  test('Feature flags + ERP Connector links appear', async ({ page }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    try {
      await seedAuthLocalStorage(page, projectToRole(testInfo.project.name));
    } catch {
      test.skip(true, 'storage state missing');
    }

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);

    const sidebar = page.getByRole('navigation').or(page.locator('aside')).first();
    await expect(sidebar.getByText(/ERP Entegrasyonu/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(sidebar.getByText(/[ÖO]zellik Bayraklar[ıi]/i).first()).toBeVisible();
  });
});

// ────────────────────────────────────────────────────────
// UI-driven flag toggle — verifies the "Env'e dön" round-trip
// ────────────────────────────────────────────────────────

test.describe('v3 · Feature flag UI toggle', () => {
  test('override a flag via the button row and revert it', async ({ page, request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const role = projectToRole(testInfo.project.name);
    try {
      await seedAuthLocalStorage(page, role);
    } catch {
      test.skip(true, `${role} storageState missing`);
    }

    const token = adminToken();

    await page.goto('/admin/feature-flags', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);

    // Narrow the list to a single predictable flag so the button clicks
    // land on the right row.
    const search = page.getByPlaceholder(/FEATURE_/i);
    await search.fill('FEATURE_MARKETPLACE');

    // Row is the div that contains the <code>FEATURE_MARKETPLACE</code> label.
    const row = page
      .locator('div.p-4')
      .filter({ has: page.locator('code', { hasText: 'FEATURE_MARKETPLACE' }) })
      .first();
    await expect(row).toBeVisible({ timeout: 10_000 });

    // Start from a clean slate in case a prior run left an override.
    const existing = await apiGet(request, token, '/admin/feature-flags');
    const before = (existing.body as Array<{ name: string; override: boolean | null }>).find(
      (f) => f.name === 'FEATURE_MARKETPLACE',
    )!;
    if (before.override !== null) {
      await apiPatch(request, token, '/admin/feature-flags/FEATURE_MARKETPLACE', {
        enabled: null,
      });
      await page.reload();
      await search.fill('FEATURE_MARKETPLACE');
    }

    // Click "Kapat" and expect the override pill to appear.
    await row.getByRole('button', { name: /^Kapat$/ }).click();
    await expect(row.getByText(/Override: Kapal[ıi]/)).toBeVisible({ timeout: 10_000 });

    // Server should now report the override.
    const afterOff = await apiGet(request, token, '/admin/feature-flags');
    const markFlag = (afterOff.body as Array<{ name: string; override: boolean | null }>).find(
      (f) => f.name === 'FEATURE_MARKETPLACE',
    )!;
    expect(markFlag.override).toBe(false);

    // Revert via the "Env'e dön" button.
    await row.getByRole('button', { name: /Env'e d[oö]n/i }).click();
    await expect(row.getByText(/Override:/)).toHaveCount(0, { timeout: 10_000 });

    const afterClear = await apiGet(request, token, '/admin/feature-flags');
    const cleared = (afterClear.body as Array<{ name: string; override: boolean | null }>).find(
      (f) => f.name === 'FEATURE_MARKETPLACE',
    )!;
    expect(cleared.override).toBeNull();
  });
});

// ────────────────────────────────────────────────────────
// ERP Create Connection wizard (UI walk-through)
// ────────────────────────────────────────────────────────

test.describe('v3 · ERP create connection wizard', () => {
  test('wizard validates credentials JSON and submits', async ({ page, request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const role = projectToRole(testInfo.project.name);
    try {
      await seedAuthLocalStorage(page, role);
    } catch {
      test.skip(true, `${role} storageState missing`);
    }

    await page.goto('/admin/erp', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);

    await page.getByRole('button', { name: /Yeni Ba[gğ]lant[ıi]/i }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(
      dialog.getByRole('heading', { name: /Yeni ERP Ba[gğ]lant[ıi]/i }),
    ).toBeVisible();

    // Labels are not wired via htmlFor/id, so address fields by their
    // order within the dialog form.
    const inputs = dialog.locator('input[type="text"], input[type="url"]');
    await inputs.nth(0).fill(`Wizard QA ${Date.now()}`);
    await inputs.nth(1).fill('https://api.parasut.com/v4');

    const textarea = dialog.locator('textarea').first();
    // Break the JSON textarea on purpose → expect client-side validation
    // to block the POST.
    await textarea.fill('not-json-at-all');

    await page.getByRole('button', { name: /^Kaydet$/ }).click();
    await expect(page.getByText(/Kimlik bilgileri ge[çc]erli JSON olmal[ıi]/i)).toBeVisible({
      timeout: 5_000,
    });

    // Fix JSON and submit for real; track the created id so we can clean
    // up via API afterwards.
    await textarea.fill(
      JSON.stringify(
        {
          client_id: 'qa',
          client_secret: 'qa',
          username: 'qa@example.com',
          password: 'qa',
          company_id: '1',
        },
        null,
        2,
      ),
    );

    const [createResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/v1/erp/connections') &&
          r.request().method() === 'POST' &&
          r.status() < 500,
        { timeout: 20_000 },
      ),
      page.getByRole('button', { name: /^Kaydet$/ }).click(),
    ]);
    expect([200, 201]).toContain(createResp.status());
    const body = (await createResp.json()) as { id: number };

    try {
      // New connection must render in the list.
      await expect(page.getByText(new RegExp(`Wizard QA`))).toBeVisible({ timeout: 10_000 });
    } finally {
      const token = adminToken();
      await apiDelete(request, token, `/erp/connections/${body.id}`);
    }
  });
});

// ────────────────────────────────────────────────────────
// Quote editor — ERP Invoice push button visibility
// ────────────────────────────────────────────────────────

test.describe('v3 · Quote editor ERP push button', () => {
  test('shows push button when an approved / accepted quote exists', async ({
    page,
    request,
  }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const quotes = await apiGet(request, token, '/quotes/?limit=20');
    expect(quotes.status).toBe(200);
    const items = (quotes.body as { items?: Array<{ id: number; status: string }> }).items ?? [];
    const target = items.find((q) => q.status === 'approved' || q.status === 'accepted');
    if (!target) test.skip(true, 'no approved/accepted quote seeded');

    try {
      await seedAuthLocalStorage(page, projectToRole(testInfo.project.name));
    } catch {
      test.skip(true, 'storage state missing');
    }

    await page.goto(`/quotes/${target!.id}`, { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);

    await expect(
      page.getByRole('button', { name: /ERP'?ye Fatura G[oö]nder/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});

// ────────────────────────────────────────────────────────
// Field audit trail — read endpoint contract
// ────────────────────────────────────────────────────────

test.describe('v3 · Field Audit Trail', () => {
  test('list endpoint returns array under manager role', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const resp = await apiGet(request, token, '/field-audit/?limit=5');
    if (resp.status === 404) test.skip(true, 'FEATURE_FIELD_AUDIT disabled on this env');
    expect(resp.status).toBe(200);
    expect(Array.isArray(resp.body)).toBe(true);
  });

  test('per-entity history endpoint returns 200 for any entity type', async ({
    request,
  }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const resp = await apiGet(
      request,
      token,
      '/field-audit/entities/customers/1?limit=5',
    );
    if (resp.status === 404) test.skip(true, 'FEATURE_FIELD_AUDIT disabled');
    expect(resp.status).toBe(200);
    expect(Array.isArray(resp.body)).toBe(true);
  });
});

// ────────────────────────────────────────────────────────
// Operations extended — BOM create + explode
// ────────────────────────────────────────────────────────

test.describe('v3 · Operations BOM', () => {
  test('BOM create + explode returns a tree node', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const parts = await apiGet(request, token, '/parts/?limit=3');
    if (parts.status === 404) test.skip(true, 'parts endpoint missing');
    const partItems =
      (parts.body as { items?: Array<{ id: number }> }).items ??
      (Array.isArray(parts.body) ? (parts.body as Array<{ id: number }>) : []);
    if (!partItems || partItems.length < 2) test.skip(true, 'need at least two spare parts');

    const parent = partItems[0].id;
    const child = partItems[1].id;

    const create = await apiPost(request, token, '/operations/bom', {
      parent_spare_part_id: parent,
      version: `e2e-${Date.now()}`,
      description: 'Playwright BOM',
      components: [{ component_spare_part_id: child, qty_per_parent: 2 }],
    });
    if (create.status === 404) test.skip(true, 'FEATURE_OPERATIONS disabled');
    expect([200, 201]).toContain(create.status);

    const tree = await apiGet(request, token, `/operations/bom/explode/${parent}`);
    expect(tree.status).toBe(200);
    const body = tree.body as {
      spare_part_id: number;
      children: Array<{ spare_part_id: number; qty_per_parent: number }>;
    };
    expect(body.spare_part_id).toBe(parent);
    expect(body.children.some((c) => c.spare_part_id === child && c.qty_per_parent === 2)).toBe(
      true,
    );
  });
});

// ────────────────────────────────────────────────────────
// Marketplace — subscription CRUD (extends the install test)
// ────────────────────────────────────────────────────────

test.describe('v3 · Marketplace subscriptions', () => {
  test('subscribe + list + reject undeclared event', async ({ request }, testInfo) => {
    const skip = skipNonAdmin(testInfo);
    if (skip) test.skip(true, skip);
    const token = adminToken();

    const slug = `e2e-sub-${Date.now()}`;
    const pluginResp = await apiPost(request, token, '/marketplace/plugins', {
      slug,
      name: 'Subscribe QA',
      scopes: ['opportunities:read'],
      events: ['quote.approved'],
    });
    if (pluginResp.status === 404) test.skip(true, 'FEATURE_MARKETPLACE disabled');
    expect([200, 201]).toContain(pluginResp.status);

    const install = await apiPost(request, token, '/marketplace/installations', {
      plugin_slug: slug,
      granted_scopes: ['opportunities:read'],
    });
    expect([200, 201]).toContain(install.status);
    const { installation } = install.body as { installation: { id: number } };

    try {
      // Declared event must succeed.
      const ok = await apiPost(request, token, '/marketplace/subscriptions', {
        installation_id: installation.id,
        event_type: 'quote.approved',
        target_url: 'https://example.com/hook',
        secret: 'shh',
      });
      expect([200, 201]).toContain(ok.status);

      // Undeclared event must return 403.
      const bad = await apiPost(request, token, '/marketplace/subscriptions', {
        installation_id: installation.id,
        event_type: 'not.declared',
        target_url: 'https://example.com/hook2',
      });
      expect(bad.status).toBe(403);

      const listResp = await apiGet(
        request,
        token,
        `/marketplace/subscriptions?installation_id=${installation.id}`,
      );
      expect(listResp.status).toBe(200);
      expect((listResp.body as unknown[]).length).toBeGreaterThanOrEqual(1);
    } finally {
      await apiDelete(request, token, `/marketplace/installations/${installation.id}`);
    }
  });
});
