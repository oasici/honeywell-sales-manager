import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E config — see e2e/*.spec.ts
 *
 * Install:
 *   npm install -D @playwright/test
 *   npx playwright install chromium
 *
 * Run against a running sandbox:
 *   docker compose -f docker-compose.sandbox.yml up -d
 *   npx playwright test
 *
 * Run against production:
 *   E2E_BASE_URL=https://honeywell-frontend.onrender.com npx playwright test
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30 * 1000,
  expect: { timeout: 5 * 1000 },
  fullyParallel: false, // rate limits are shared across tests
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // avoid rate-limit collisions
  reporter: 'list',

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8081',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ignoreHTTPSErrors: true,
  },

  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
    },
    {
      name: 'admin',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
      storageState: 'e2e/.auth/admin.json',
    },
    {
      name: 'sales_manager',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
      storageState: 'e2e/.auth/sales_manager.json',
    },
    {
      name: 'sales_rep',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
      storageState: 'e2e/.auth/sales_rep.json',
    },
    {
      name: 'operations',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
      storageState: 'e2e/.auth/operations.json',
    },
  ],
});
