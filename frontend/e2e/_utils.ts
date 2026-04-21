import type { Page, APIRequestContext, TestInfo } from '@playwright/test';
import { expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

export const E2E_BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8081';
export const E2E_API_BASE_URL = process.env.E2E_API_BASE_URL ?? E2E_BASE_URL;
export const E2E_ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'admin@honeywell.com';
export const E2E_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'Honeywell2026!';

export type E2ERole = 'admin' | 'sales_manager' | 'sales_rep' | 'operations';

export function roleCreds(role: E2ERole): { email: string | null; password: string | null } {
  switch (role) {
    case 'admin':
      return {
        email: process.env.E2E_ADMIN_EMAIL ?? null,
        password: process.env.E2E_ADMIN_PASSWORD ?? null,
      };
    case 'sales_manager':
      return {
        email: process.env.E2E_SALES_MANAGER_EMAIL ?? null,
        password: process.env.E2E_SALES_MANAGER_PASSWORD ?? null,
      };
    case 'sales_rep':
      return {
        email: process.env.E2E_SALES_REP_EMAIL ?? null,
        password: process.env.E2E_SALES_REP_PASSWORD ?? null,
      };
    case 'operations':
      return {
        email: process.env.E2E_OPERATIONS_EMAIL ?? null,
        password: process.env.E2E_OPERATIONS_PASSWORD ?? null,
      };
  }
}

export function storageStatePath(role: E2ERole): string {
  return `e2e/.auth/${role}.json`;
}

export function projectToRole(projectName: string | undefined): E2ERole {
  if (projectName === 'admin') return 'admin';
  if (projectName === 'sales_manager') return 'sales_manager';
  if (projectName === 'sales_rep') return 'sales_rep';
  if (projectName === 'operations') return 'operations';
  // default fallback
  return 'admin';
}

export async function uiLogin(page: Page) {
  await page.goto('/login', { waitUntil: 'domcontentloaded' });

  // Already logged in (rare but possible if storageState reused)
  if (!page.url().includes('/login')) return;

  await page.getByLabel('E-posta').fill(E2E_ADMIN_EMAIL);
  await page.getByLabel('Sifre').fill(E2E_ADMIN_PASSWORD);

  const [loginResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST',
      {
        timeout: 60_000,
      },
    ),
    page.getByRole('button', { name: /Giris Yap/i }).click(),
  ]);

  if (loginResponse.status() !== 200) {
    const body = await loginResponse.text();
    throw new Error(`Login failed: ${loginResponse.status()} ${body.slice(0, 500)}`);
  }

  // SPA navigation: URL can change without a full load event
  await page.waitForTimeout(250);
  if (page.url().includes('/login')) {
    // Some deployments may not change URL immediately; force a route and validate shell.
    await page.goto('/', { waitUntil: 'domcontentloaded' });
  }

  // Ensure some authenticated shell appears
  await expect(page).not.toHaveURL(/\/login/);
}

export async function expectNotStuckLoading(page: Page, testInfo: TestInfo, timeoutMs = 12_000) {
  // If a lazy chunk fails to load, Suspense fallback spinner can stay.
  // The app's LoadingSpinner has an escape hatch after ~6s (see LoadingSpinner.tsx).
  // We still want to fail if we see that "still loading" screen.
  const stillLoadingHeading = page.getByText('Sayfa beklenenden uzun suredir yükleniyor', {
    exact: false,
  });

  const loadingSpinner = page.getByLabel('Yükleniyor');

  // Wait a bit for content OR for "still loading" escape to appear
  await Promise.race([
    stillLoadingHeading.waitFor({ state: 'visible', timeout: timeoutMs }).then(() => 'timed_out'),
    page
      .waitForLoadState('networkidle', { timeout: timeoutMs })
      .then(() => 'idle')
      .catch(() => 'idle'),
    loadingSpinner
      .waitFor({ state: 'detached', timeout: timeoutMs })
      .then(() => 'spinner_gone')
      .catch(() => 'spinner_gone'),
  ]);

  if (await stillLoadingHeading.isVisible()) {
    await testInfo.attach('stuck-loading-url', {
      body: Buffer.from(page.url()),
      contentType: 'text/plain',
    });
    throw new Error(`Sayfa loading ekranında takıldı: ${page.url()}`);
  }
}

export async function apiLoginAndGetToken(request: APIRequestContext) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const r = await request.post(`${E2E_API_BASE_URL}/api/v1/auth/login`, {
      form: { username: E2E_ADMIN_EMAIL, password: E2E_ADMIN_PASSWORD },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    const text = await r.text();
    if (r.status() === 429 && attempt < 3) {
      // Avoid poisoning the whole suite if rate limit is temporarily high.
      await new Promise((res) => setTimeout(res, 1200 * attempt));
      continue;
    }
    expect(r.status(), text).toBe(200);
    const json = JSON.parse(text) as { access_token?: string };
    expect(json.access_token).toBeTruthy();
    return json.access_token!;
  }
  throw new Error('Unreachable');
}

export async function withAuthHeader(
  request: APIRequestContext,
  token: string,
  url: string,
): Promise<{ status: number; bodySnippet: string }> {
  const r = await request.get(url, { headers: { Authorization: `Bearer ${token}` } });
  const text = await r.text();
  return { status: r.status(), bodySnippet: text.slice(0, 300) };
}

export function captureConsoleErrorsOnPage(page: Page) {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(String(err)));
  return errors;
}

export async function attachConsoleErrors(testInfo: TestInfo, errors: string[]) {
  if (errors.length === 0) return;
  await testInfo.attach('console-errors', {
    body: Buffer.from(errors.join('\n\n')),
    contentType: 'text/plain',
  });
}

export function readAdminStorageState() {
  const storagePath = path.join(process.cwd(), 'e2e/.auth/admin.json');
  const storage = JSON.parse(fs.readFileSync(storagePath, 'utf8')) as {
    origins?: Array<{ origin: string; localStorage?: Array<{ name: string; value: string }> }>;
  };
  const origin = storage.origins?.[0];
  const ls = origin?.localStorage ?? [];
  const token = ls.find((i) => i.name === 'token')?.value ?? null;
  const refreshToken = ls.find((i) => i.name === 'refreshToken')?.value ?? null;
  const user = ls.find((i) => i.name === 'user')?.value ?? null;
  return { token, refreshToken, user };
}

export function readStorageState(role: E2ERole) {
  const storagePath = path.join(process.cwd(), storageStatePath(role));
  if (!fs.existsSync(storagePath)) {
    return { token: null, refreshToken: null, user: null };
  }
  const storage = JSON.parse(fs.readFileSync(storagePath, 'utf8')) as {
    origins?: Array<{ origin: string; localStorage?: Array<{ name: string; value: string }> }>;
  };
  const origin = storage.origins?.[0];
  const ls = origin?.localStorage ?? [];
  const token = ls.find((i) => i.name === 'token')?.value ?? null;
  const refreshToken = ls.find((i) => i.name === 'refreshToken')?.value ?? null;
  const user = ls.find((i) => i.name === 'user')?.value ?? null;
  return { token, refreshToken, user };
}

export async function seedAuthLocalStorage(page: Page, role: E2ERole) {
  const { token, refreshToken, user } = readStorageState(role);
  if (!token || !refreshToken || !user) throw new Error('Missing auth items in storageState');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ t, rt, u }) => {
      localStorage.setItem('token', t);
      localStorage.setItem('refreshToken', rt);
      localStorage.setItem('user', u);
    },
    { t: token, rt: refreshToken, u: user },
  );
}

export function hasRoleCreds(role: E2ERole): boolean {
  const { email, password } = roleCreds(role);
  return !!email && !!password;
}
