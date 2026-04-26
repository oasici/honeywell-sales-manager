import { test, expect } from '@playwright/test';
import {
  withAuthHeader,
  E2E_API_BASE_URL,
  projectToRole,
  readStorageState,
  hasRoleCreds,
} from './_utils';

test.describe('Full API smoke (admin token)', () => {
  test('core endpoints return 2xx', async ({ request }) => {
    // Reuse UI auth storageState token to avoid hitting login rate limits in prod.
    const role = projectToRole(test.info().project.name);
    if (!hasRoleCreds(role)) test.skip(true, `${role} creds not set`);
    const { token } = readStorageState(role);
    if (!token) test.skip(true, `${role} storageState missing (setup role login failed)`);

    const checks: Array<{ name: string; url: string; allow403?: boolean }> = [
      { name: 'health', url: `${E2E_API_BASE_URL}/api/health` },
      { name: 'root liveness', url: `${E2E_API_BASE_URL}/` },
      { name: 'me', url: `${E2E_API_BASE_URL}/api/v1/auth/me` },
      {
        name: 'dashboard stats',
        url: `${E2E_API_BASE_URL}/api/v1/dashboard/stats`,
        allow403: role === 'operations',
      },
      {
        name: 'emails',
        url: `${E2E_API_BASE_URL}/api/v1/emails/?page=1&page_size=20`,
        allow403: role === 'operations',
      },
      {
        name: 'customers',
        url: `${E2E_API_BASE_URL}/api/v1/customers/?page=1&page_size=20`,
        allow403: role === 'operations',
      },
      {
        name: 'quotes',
        url: `${E2E_API_BASE_URL}/api/v1/quotes/?page=1&page_size=20`,
        allow403: role === 'operations',
      },
      {
        name: 'parts',
        url: `${E2E_API_BASE_URL}/api/v1/parts/?page=1&page_size=20`,
        allow403: role === 'operations',
      },
      {
        name: 'opportunities',
        url: `${E2E_API_BASE_URL}/api/v1/opportunities/?page=1&page_size=20`,
        allow403: role === 'operations',
      },
      {
        name: 'cockpit kpis',
        url: `${E2E_API_BASE_URL}/api/v1/cockpit/kpis`,
        allow403: role === 'operations',
      },
      {
        name: 'cockpit signals',
        url: `${E2E_API_BASE_URL}/api/v1/cockpit/signals?limit=5`,
        allow403: role === 'operations',
      },
      // V4 cockpit additions (gated by FEATURE_REVENUE_COCKPIT — 404 when off)
      {
        name: 'cockpit momentum',
        url: `${E2E_API_BASE_URL}/api/v1/cockpit/momentum?limit=5`,
        allow403: role === 'operations',
      },
      {
        name: 'cockpit buyer-state stalling',
        url: `${E2E_API_BASE_URL}/api/v1/cockpit/buyer-state/stalling?limit=5`,
        allow403: role === 'operations',
      },
      // V4 standalone surfaces (gated by FEATURE_V4_*)
      {
        name: 'decision gaps cockpit list',
        url: `${E2E_API_BASE_URL}/api/v1/decision-gaps/cockpit/list?limit=5`,
        allow403: role === 'operations',
      },
      {
        name: 'network benchmarks latest',
        url: `${E2E_API_BASE_URL}/api/v1/network-benchmarks/segments`,
        allow403: role === 'operations' || role === 'sales_rep',
      },

      // PR-2.2: extended audit endpoints (manager-only)
      {
        name: 'audit list with action_prefix filter',
        url: `${E2E_API_BASE_URL}/api/v1/audit/?action_prefix=kvkk_&page_size=5`,
        allow403: role === 'sales_rep' || role === 'operations',
      },
      {
        name: 'audit CSV export',
        url: `${E2E_API_BASE_URL}/api/v1/audit/export/csv?page_size=5`,
        allow403: role === 'sales_rep' || role === 'operations',
      },
      {
        name: 'workflow rules',
        url: `${E2E_API_BASE_URL}/api/v1/workflow-rules/`,
        allow403: role === 'sales_rep' || role === 'operations',
      },

      // Strict: these were returning 404 in live; keep them as canary.
      {
        name: 'engagement sequences',
        url: `${E2E_API_BASE_URL}/api/v1/engagement/sequences/`,
        allow403: role === 'operations',
      },
      {
        name: 'engagement segments',
        url: `${E2E_API_BASE_URL}/api/v1/engagement/segments/`,
        allow403: role === 'operations',
      },

      {
        name: 'playbooks templates',
        url: `${E2E_API_BASE_URL}/api/v1/playbooks/templates`,
        allow403: role === 'operations',
      },
    ];

    const failures: string[] = [];
    for (const c of checks) {
      if (c.name === 'health') {
        const r = await request.get(c.url);
        const text = await r.text();
        if (r.status() < 200 || r.status() >= 300)
          failures.push(`${c.name}: ${r.status()} (${c.url})\n${text.slice(0, 300)}`);
        continue;
      }

      const { status, bodySnippet } = await withAuthHeader(request, token, c.url);
      const ok = (status >= 200 && status < 300) || (c.allow403 && status === 403);
      if (!ok) failures.push(`${c.name}: ${status} (${c.url})\n${bodySnippet}`);
    }

    expect(failures.join('\n\n')).toBe('');
  });

  // PR-1.1: /api/health now exposes circuit breaker state. Operators
  // and uptime monitors rely on this contract; lock the shape here.
  test('health endpoint exposes circuits + status', async ({ request }) => {
    const r = await request.get(`${E2E_API_BASE_URL}/api/health`);
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(['healthy', 'degraded']).toContain(body.status);
    expect(body.circuits).toBeDefined();
    for (const name of ['claude_api', 'graph_api', 'currency_api', 'qdrant']) {
      expect(body.circuits[name], `breaker '${name}' missing`).toBeDefined();
      expect(['closed', 'open', 'half_open']).toContain(body.circuits[name].state);
    }
  });

  // PR-4.4 / UptimeRobot fix: health endpoint must accept HEAD too.
  test('health endpoint accepts HEAD', async ({ request }) => {
    const r = await request.fetch(`${E2E_API_BASE_URL}/api/health`, { method: 'HEAD' });
    expect(r.status()).toBe(200);
  });
});
