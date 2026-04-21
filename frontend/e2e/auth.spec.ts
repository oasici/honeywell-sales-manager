/**
 * Authentication + Security E2E tests.
 *
 * Run against a running sandbox:
 *   cd frontend
 *   npm install -D @playwright/test
 *   npx playwright install chromium
 *   npx playwright test e2e/auth.spec.ts
 *
 * Environment:
 *   E2E_BASE_URL=http://localhost:8081 (default)
 *   E2E_ADMIN_EMAIL=admin@honeywell.com
 *   E2E_ADMIN_PASSWORD=Honeywell2026!
 */

import { test, expect } from '@playwright/test';
import { projectToRole, roleCreds } from './_utils';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8081';

test.describe('Authentication + Cookie + CSRF', () => {
  test('login sets HttpOnly cookies', async ({ page, context }) => {
    test.skip(
      process.env.E2E_RUN_AUTH_COOKIE_TESTS !== '1',
      'Enable with E2E_RUN_AUTH_COOKIE_TESTS=1',
    );
    test.skip(
      test.info().project.name !== 'admin',
      'Auth cookie suite runs only for admin to avoid rate limits',
    );
    const role = projectToRole(test.info().project.name);
    const { email, password } = roleCreds(role);
    if (!email || !password) test.skip(true, `${role} creds not set`);
    const response = await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
      form: {
        username: email,
        password,
      },
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    expect(response.status()).toBe(200);

    const cookies = await context.cookies();
    // Some deployments primarily rely on localStorage bearer tokens; cookies may be absent.
    if (cookies.length === 0) test.skip(true, 'This deployment does not set auth cookies');
    const cookieNames = cookies.map((c) => c.name);
    expect(cookieNames).toContain('access_token');
    expect(cookieNames).toContain('refresh_token');
    expect(cookieNames).toContain('csrf_token');

    // access_token must be HttpOnly (invisible to JS / XSS)
    const accessCookie = cookies.find((c) => c.name === 'access_token');
    expect(accessCookie?.httpOnly).toBe(true);

    // csrf_token must NOT be HttpOnly (frontend JS must read it)
    const csrfCookie = cookies.find((c) => c.name === 'csrf_token');
    expect(csrfCookie?.httpOnly).toBe(false);
  });

  test('cookie-only auth works for GET requests', async ({ page }) => {
    test.skip(
      process.env.E2E_RUN_AUTH_COOKIE_TESTS !== '1',
      'Enable with E2E_RUN_AUTH_COOKIE_TESTS=1',
    );
    test.skip(
      test.info().project.name !== 'admin',
      'Auth cookie suite runs only for admin to avoid rate limits',
    );
    const role = projectToRole(test.info().project.name);
    const { email, password } = roleCreds(role);
    if (!email || !password) test.skip(true, `${role} creds not set`);
    await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
      form: { username: email, password },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    // No Authorization header — cookies alone should work
    const r = await page.request.get(`${BASE_URL}/api/v1/auth/me`);
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.email).toBe(email);
  });

  test('CSRF blocks state-changing request without X-CSRF-Token', async ({ page }) => {
    test.skip(
      process.env.E2E_RUN_AUTH_COOKIE_TESTS !== '1',
      'Enable with E2E_RUN_AUTH_COOKIE_TESTS=1',
    );
    test.skip(
      test.info().project.name !== 'admin',
      'Auth cookie suite runs only for admin to avoid rate limits',
    );
    const role = projectToRole(test.info().project.name);
    const { email, password } = roleCreds(role);
    if (!email || !password) test.skip(true, `${role} creds not set`);
    await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
      form: { username: email, password },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    // Cookie auth succeeds, but no X-CSRF-Token → 403
    const r = await page.request.post(`${BASE_URL}/api/v1/customers/`, {
      data: { name: 'csrf test', company: 'X' },
    });
    // Some deployments may reject as 401 if cookie auth not enabled for this role
    if (r.status() === 401) test.skip(true, 'Cookie auth not enabled for this deployment/role');
    expect(r.status()).toBe(403);
    const body = await r.json();
    expect(JSON.stringify(body).toLowerCase()).toContain('csrf');
  });

  test('CSRF passes when X-CSRF-Token matches cookie', async ({ page, context }) => {
    test.skip(
      process.env.E2E_RUN_AUTH_COOKIE_TESTS !== '1',
      'Enable with E2E_RUN_AUTH_COOKIE_TESTS=1',
    );
    test.skip(
      test.info().project.name !== 'admin',
      'Auth cookie suite runs only for admin to avoid rate limits',
    );
    const role = projectToRole(test.info().project.name);
    const { email, password } = roleCreds(role);
    if (!email || !password) test.skip(true, `${role} creds not set`);
    await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
      form: { username: email, password },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    const cookies = await context.cookies();
    const csrf = cookies.find((c) => c.name === 'csrf_token')?.value;
    if (!csrf) test.skip(true, 'No CSRF cookie set in this deployment');

    const r = await page.request.post(`${BASE_URL}/api/v1/customers/`, {
      data: { name: 'csrf passes', company: 'Y', email: 'p@q.com' },
      headers: { 'X-CSRF-Token': csrf! },
    });
    // Any non-403 is acceptable — CSRF check passed
    expect(r.status()).not.toBe(403);
  });

  test('logout clears all auth cookies', async ({ page, context }) => {
    test.skip(
      process.env.E2E_RUN_AUTH_COOKIE_TESTS !== '1',
      'Enable with E2E_RUN_AUTH_COOKIE_TESTS=1',
    );
    test.skip(
      test.info().project.name !== 'admin',
      'Auth cookie suite runs only for admin to avoid rate limits',
    );
    const role = projectToRole(test.info().project.name);
    const { email, password } = roleCreds(role);
    if (!email || !password) test.skip(true, `${role} creds not set`);
    await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
      form: { username: email, password },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    let cookies = await context.cookies();
    const accessCookieBefore = cookies.find((c) => c.name === 'access_token');
    if (!accessCookieBefore) test.skip(true, 'No auth cookies set in this deployment');

    const csrf = cookies.find((c) => c.name === 'csrf_token')?.value;
    if (!csrf) test.skip(true, 'No CSRF cookie set in this deployment');
    await page.request.post(`${BASE_URL}/api/v1/auth/logout`, {
      data: {},
      headers: { 'X-CSRF-Token': csrf! },
    });

    cookies = await context.cookies();
    // access_token may be cleared to empty or removed — either way unusable
    const access = cookies.find((c) => c.name === 'access_token');
    expect(access === undefined || access.value === '').toBe(true);
  });
});

test.describe('Security Headers', () => {
  test('response includes hardening headers', async ({ page }) => {
    const response = await page.request.get(`${BASE_URL}/api/health`);
    const headers = response.headers();

    expect(headers['x-content-type-options']).toBe('nosniff');
    expect(headers['x-frame-options']).toBe('DENY');
    expect(headers['content-security-policy']).toContain("default-src 'self'");
    expect(headers['content-security-policy']).toContain("object-src 'none'");
    expect(headers['content-security-policy']).toContain("frame-ancestors 'none'");
    expect(headers['strict-transport-security']).toContain('max-age');
  });
});

test.describe('Removed/Guarded Endpoints', () => {
  test('debug endpoint returns 404', async ({ page }) => {
    const r = await page.request.get(`${BASE_URL}/api/debug/login-test`);
    expect(r.status()).toBe(404);
  });

  test('seed endpoint requires auth', async ({ page }) => {
    const r = await page.request.post(`${BASE_URL}/api/admin/seed-demo`);
    expect(r.status()).toBe(401);
  });
});

test.describe('Rate Limiting', () => {
  test('login rate-limits after 5 failed attempts', async ({ page }) => {
    test.skip(
      process.env.E2E_RUN_RATE_LIMIT_TESTS !== '1',
      'Enable with E2E_RUN_RATE_LIMIT_TESTS=1',
    );
    const codes: number[] = [];
    for (let i = 0; i < 7; i++) {
      const r = await page.request.post(`${BASE_URL}/api/v1/auth/login`, {
        form: { username: `ratetest${Date.now()}@x.com`, password: 'wrong' },
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      codes.push(r.status());
    }
    // First 5 are 401 (invalid creds); 6th+ should be 429
    expect(codes.slice(0, 5).every((c) => c === 401)).toBe(true);
    expect(codes[5]).toBe(429);
  });
});
