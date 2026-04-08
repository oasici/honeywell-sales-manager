import { test, expect } from '@playwright/test';

type RoleKey = 'admin' | 'sales_manager' | 'sales_rep' | 'operations';

function creds(role: RoleKey) {
  const map = {
    admin: {
      email: process.env.E2E_ADMIN_EMAIL,
      password: process.env.E2E_ADMIN_PASSWORD,
      expectedRoleLabel: 'Yönetici',
      canSeeReports: true,
    },
    sales_manager: {
      email: process.env.E2E_MANAGER_EMAIL,
      password: process.env.E2E_MANAGER_PASSWORD,
      expectedRoleLabel: 'Satış Müdürü',
      canSeeReports: true,
    },
    sales_rep: {
      email: process.env.E2E_REP_EMAIL,
      password: process.env.E2E_REP_PASSWORD,
      expectedRoleLabel: 'Satış Temsilcisi',
      canSeeReports: false,
    },
    operations: {
      email: process.env.E2E_OPS_EMAIL,
      password: process.env.E2E_OPS_PASSWORD,
      // Header falls back to raw role string if missing in ROLE_LABELS.
      expectedRoleLabel: 'operations',
      canSeeReports: false,
    },
  } as const;

  const v = map[role];
  if (!v.email || !v.password || v.password === 'CHANGEME') {
    throw new Error(
      `Missing E2E creds for ${role}. Set env vars (see .env.e2e.example).`,
    );
  }
  return v;
}

async function login(page: any, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('E-posta').fill(email);
  await page.getByLabel('Sifre').fill(password);
  await page.getByRole('button', { name: 'Giris Yap' }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

async function logoutIfPossible(page: any) {
  const logoutButton = page.getByTitle('Cikis Yap');
  if (await logoutButton.count()) {
    await logoutButton.click();
    await expect(page).toHaveURL(/\/login$/);
  }
}

test.describe('Auth smoke by role', () => {
  for (const role of ['admin', 'sales_manager', 'sales_rep', 'operations'] as const) {
    test(`${role} can login and navigate core pages`, async ({ page }) => {
      const c = creds(role);
      await login(page, c.email, c.password);

      // Evidence
      await page.screenshot({ path: `test-results/${role}-after-login.png`, fullPage: true });

      // Header: role badge exists (or fallback role string)
      await expect(page.getByText(c.expectedRoleLabel, { exact: false })).toBeVisible();

      // Core navigation (non-destructive).
      // These links are in Sidebar with translated labels; target by route via URL navigation.
      await page.goto('/emails');
      await expect(page).toHaveURL(/\/emails/);

      await page.goto('/quotes');
      await expect(page).toHaveURL(/\/quotes/);

      await page.goto('/customers');
      await expect(page).toHaveURL(/\/customers/);

      await page.goto('/settings');
      await expect(page).toHaveURL(/\/settings/);

      // Reports access expectation: reps/ops should be blocked (redirect or forbidden page)
      await page.goto('/reports');
      if (c.canSeeReports) {
        await expect(page).toHaveURL(/\/reports/);
      } else {
        // Accept either redirect away or visible forbidden text.
        await expect(page).not.toHaveURL(/\/reports$/);
        await page.screenshot({ path: `test-results/${role}-reports-blocked.png`, fullPage: true });
      }

      await logoutIfPossible(page);
    });
  }
});

test('sales_rep cannot access random email/quote detail by URL tampering (best-effort)', async ({ page }) => {
  const c = creds('sales_rep');
  await login(page, c.email, c.password);

  // Get one visible email id from the list by clicking first detail link if present.
  await page.goto('/emails');
  const emailLink = page.locator('a[href^="/emails/"]').first();
  if (await emailLink.count()) {
    const href = await emailLink.getAttribute('href');
    if (href) {
      await page.goto(href);
      await expect(page).toHaveURL(/\/emails\/\d+/);

      const match = page.url().match(/\/emails\/(\d+)/);
      const id = match ? Number(match[1]) : null;
      if (id && id > 1) {
        // Tamper: try nearby id
        await page.goto(`/emails/${id - 1}`);
        // Should not show the page as accessible. Accept redirect or forbidden UI.
        await expect(page).not.toHaveURL(new RegExp(`/emails/${id - 1}$`));
      }
    }
  }

  await page.goto('/quotes');
  const quoteLink = page.locator('a[href^="/quotes/"]').first();
  if (await quoteLink.count()) {
    const href = await quoteLink.getAttribute('href');
    if (href) {
      await page.goto(href);
      await expect(page).toHaveURL(/\/quotes\/\d+/);

      const match = page.url().match(/\/quotes\/(\d+)/);
      const id = match ? Number(match[1]) : null;
      if (id && id > 1) {
        await page.goto(`/quotes/${id - 1}`);
        await expect(page).not.toHaveURL(new RegExp(`/quotes/${id - 1}$`));
      }
    }
  }
});

