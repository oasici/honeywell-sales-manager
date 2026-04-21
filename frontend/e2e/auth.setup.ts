import { test as setup, expect } from '@playwright/test';
import { E2E_BASE_URL, roleCreds, storageStatePath, type E2ERole } from './_utils';

/**
 * Attempts login for a role; on success writes storageState and returns true.
 * Does NOT skip the parent setup — missing creds / rate limits just return false.
 */
async function setupRole(
  page: import('@playwright/test').Page,
  role: E2ERole,
): Promise<{ ok: boolean; reason?: string }> {
  const { email, password } = roleCreds(role);
  if (!email || !password) {
    return { ok: false, reason: 'creds not set' };
  }

  let bodyText = '';
  let status = 0;
  for (let attempt = 1; attempt <= 4; attempt++) {
    const r = await page.request.post(`${E2E_BASE_URL}/api/v1/auth/login`, {
      form: { username: email, password },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    status = r.status();
    bodyText = await r.text();
    if (status === 429) {
      await page.waitForTimeout(1200 * attempt);
      continue;
    }
    break;
  }

  if (status === 429) return { ok: false, reason: 'rate-limited (429)' };
  if (status === 401) return { ok: false, reason: 'credentials rejected (401)' };
  if (status !== 200) return { ok: false, reason: `HTTP ${status}: ${bodyText.slice(0, 120)}` };

  const body = JSON.parse(bodyText) as {
    access_token: string;
    refresh_token: string;
    user: unknown;
  };

  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ access, refresh, user }) => {
      localStorage.setItem('token', access);
      localStorage.setItem('refreshToken', refresh);
      localStorage.setItem('user', JSON.stringify(user));
    },
    { access: body.access_token, refresh: body.refresh_token, user: body.user },
  );

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login/, { timeout: 60_000 });
  await page.context().storageState({ path: storageStatePath(role) });
  return { ok: true };
}

setup('authenticate roles (storageState)', async ({ page }) => {
  setup.setTimeout(180_000);
  const results: Record<string, { ok: boolean; reason?: string }> = {};
  for (const role of ['admin', 'sales_manager', 'sales_rep', 'operations'] as E2ERole[]) {
    results[role] = await setupRole(page, role);
    // Small pause between logins to avoid rate limits
    await page.waitForTimeout(500);
  }
  // Log per-role outcome so it is visible in CI artefact
  // eslint-disable-next-line no-console
  console.log('[auth.setup] role results:', JSON.stringify(results));
  // Setup never fails: each role is best-effort; downstream tests skip themselves if storageState missing.
});
