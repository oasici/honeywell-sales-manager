import { test, expect } from '@playwright/test';
import {
  expectNotStuckLoading,
  captureConsoleErrorsOnPage,
  attachConsoleErrors,
  seedAuthLocalStorage,
  projectToRole,
  hasRoleCreds,
} from './_utils';

test.describe('Full UI smoke (by role)', () => {
  test('can login and visit primary pages', async ({ page }, testInfo) => {
    const consoleErrors = captureConsoleErrorsOnPage(page);

    // Ensure AuthGuard sees localStorage tokens (some deployments may clear storageState on boot).
    const role = projectToRole(testInfo.project.name);
    if (!hasRoleCreds(role)) test.skip(true, `${role} creds not set`);
    try {
      await seedAuthLocalStorage(page, role);
    } catch {
      test.skip(true, `${role} storageState missing (setup role login failed)`);
    }

    // Dashboard
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByRole('heading', { name: 'Kontrol Paneli' })).toBeVisible({
      timeout: 15_000,
    });

    // Emails
    await page.goto('/emails', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByRole('heading', { name: 'Emailler' })).toBeVisible({ timeout: 15_000 });

    // This assertion is intentionally strict: we want the test to fail if list renders empty
    // while API returns data (current known issue).
    await expect(
      page.getByText('Kayıt bulunamadı', { exact: false }),
      'Emails list is empty; likely UI render/parsing bug',
    ).not.toBeVisible({ timeout: 5_000 });

    // Customers
    await page.goto('/customers', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByRole('heading', { name: 'Müşteriler' })).toBeVisible({
      timeout: 15_000,
    });

    // Quotes
    await page.goto('/quotes', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByRole('heading', { name: 'Teklifler' })).toBeVisible({ timeout: 15_000 });

    // Parts
    await page.goto('/parts', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByRole('heading', { name: 'Yedek Parçalar' })).toBeVisible({
      timeout: 15_000,
    });

    await expect(
      page.getByText('Kayıt bulunamadı', { exact: false }),
      'Parts list is empty; likely UI render/parsing bug',
    ).not.toBeVisible({ timeout: 5_000 });

    // Sales Board
    await page.goto('/board', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByText('Sales Board', { exact: false })).toBeVisible({ timeout: 15_000 });

    // Leads
    await page.goto('/leads', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(
      page.getByRole('heading', { name: /Potansiyel Müşteriler \(Leads\)/i }),
    ).toBeVisible({
      timeout: 15_000,
    });

    // Cockpit
    await page.goto('/cockpit', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(page.getByRole('heading', { name: 'Gelir Kokpiti' })).toBeVisible({
      timeout: 15_000,
    });

    // Admin / workflow rules (visual editor list) — only for admin/sales_manager
    if (role === 'admin' || role === 'sales_manager') {
      await page.goto('/admin/workflow-rules', { waitUntil: 'domcontentloaded' });
      await expectNotStuckLoading(page, testInfo);
      await expect(page.getByRole('heading', { name: 'İş Kuralları' })).toBeVisible({
        timeout: 15_000,
      });

      await page.goto('/admin/workflow-rules/flow/new', { waitUntil: 'domcontentloaded' });
      await expectNotStuckLoading(page, testInfo);
      await expect(page.getByText('Flow', { exact: false })).toBeVisible({ timeout: 15_000 });
    }

    // Engagement sequences & segments — strict: should not be 404-backed empty page
    await page.goto('/engagement/sequences', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(
      page.getByRole('heading', { name: 'Sekanslar' }),
      'Engagement Sequences page did not render expected header',
    ).toBeVisible({ timeout: 15_000 });

    await page.goto('/engagement/segments', { waitUntil: 'domcontentloaded' });
    await expectNotStuckLoading(page, testInfo);
    await expect(
      page.getByRole('heading', { name: 'Segmentler' }),
      'Engagement Segments page did not render expected header',
    ).toBeVisible({ timeout: 15_000 });

    await attachConsoleErrors(testInfo, consoleErrors);
  });
});
