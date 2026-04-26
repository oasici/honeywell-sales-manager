#!/usr/bin/env node
/**
 * Full-page screenshot capturer for the Honeywell Sales Suite UI.
 *
 * Logs in to the configured backend, visits every routed page in turn,
 * and saves a 1920×1080 full-page PNG to ~/Downloads/honeywell-ui-screenshots/
 * (or the path you pass as the third arg).
 *
 * Usage:
 *   node scripts/capture-screenshots.mjs <email> <password> [outDir] [baseUrl]
 *
 * Examples:
 *   node scripts/capture-screenshots.mjs admin@honeywell.com 'PWD'
 *   node scripts/capture-screenshots.mjs admin@honeywell.com 'PWD' ~/Desktop/shots
 *   node scripts/capture-screenshots.mjs admin@honeywell.com 'PWD' '' http://localhost:5173
 *
 * Requires Playwright Chromium (already installed for e2e tests):
 *   npx playwright install chromium
 */

import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';

const [, , emailArg, passwordArg, outDirArg, baseUrlArg] = process.argv;

if (!emailArg || !passwordArg) {
  console.error('Usage: node scripts/capture-screenshots.mjs <email> <password> [outDir] [baseUrl]');
  process.exit(1);
}

const FRONTEND_URL = (baseUrlArg || 'https://honeywell-frontend.onrender.com').replace(/\/+$/, '');
const BACKEND_URL = FRONTEND_URL.replace('honeywell-frontend', 'honeywell-backend');
const OUT_DIR = outDirArg || path.join(homedir(), 'Downloads', 'honeywell-ui-screenshots');

// Every routed page worth a screenshot. Add/remove freely; missing routes
// just produce a 404 screenshot which is itself useful for triage.
const ROUTES = [
  ['/', 'dashboard'],
  ['/emails', 'emails'],
  ['/customers', 'customers'],
  ['/customers/high-intent', 'customers-high-intent'],
  ['/quotes', 'quotes'],
  ['/parts', 'parts'],
  ['/board', 'board-kanban'],
  ['/planning-studio', 'planning-studio'],
  ['/leads', 'leads'],
  ['/cockpit', 'cockpit'],
  ['/insights', 'insights'],
  ['/sales-analytics', 'sales-analytics'],
  ['/audit', 'audit-log'],
  ['/kvkk-export', 'kvkk-export'],
  ['/admin/users', 'admin-users'],
  ['/admin/workflow-rules', 'admin-workflow-rules'],
  ['/admin/custom-fields', 'admin-custom-fields'],
  ['/admin/field-permissions', 'admin-field-permissions'],
  ['/admin/territories', 'admin-territories'],
  ['/admin/data-quality', 'admin-data-quality'],
  ['/admin/pricing', 'admin-pricing'],
  ['/admin/chat', 'admin-live-chat'],
  ['/admin/leaderboard', 'admin-leaderboard'],
  ['/reports/saved', 'reports-saved'],
  ['/dashboards', 'dashboards-list'],
  ['/engagement/sequences', 'engagement-sequences'],
  ['/engagement/segments', 'engagement-segments'],
  ['/coaching', 'coaching'],
  ['/approvals', 'approvals'],
  ['/contracts', 'contracts'],
  ['/campaigns', 'campaigns'],
  ['/invoices', 'invoices'],
  ['/integrations', 'integrations'],
  ['/settings', 'settings'],
  ['/settings/pipelines', 'settings-pipelines'],
];

async function login(page) {
  console.log(`▶ login as ${emailArg}`);
  // Hit the backend directly; cookies + tokens land on the frontend origin
  // when we then seed them into localStorage on a frontend page.
  const response = await page.request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    form: { username: emailArg, password: passwordArg },
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  if (response.status() !== 200) {
    const body = await response.text();
    throw new Error(`Login failed ${response.status()}: ${body.slice(0, 200)}`);
  }
  const body = await response.json();
  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ access, refresh, user }) => {
      localStorage.setItem('token', access);
      localStorage.setItem('refreshToken', refresh);
      localStorage.setItem('user', JSON.stringify(user));
    },
    { access: body.access_token, refresh: body.refresh_token, user: body.user },
  );
  console.log('  login OK');
}

async function capture(page, route, slug) {
  const url = `${FRONTEND_URL}${route}`;
  const file = path.join(OUT_DIR, `${String(slug).padStart(2, '0')}.png`);
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30_000 });
  } catch {
    // Fall back to domcontentloaded; some pages keep WebSocket / poll
    // connections open so networkidle never resolves.
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15_000 });
  }
  // Wait a beat for late-mounted content (charts, lazy panels).
  await page.waitForTimeout(2000);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`  ${route.padEnd(40)} → ${path.basename(file)}`);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log(`output: ${OUT_DIR}`);
  console.log(`target: ${FRONTEND_URL}`);
  console.log('');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2, // retina-quality screenshots
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);

  // Some pages console.error without crashing — silence the noise.
  page.on('pageerror', () => {});

  try {
    await login(page);
    let i = 0;
    for (const [route, slug] of ROUTES) {
      i += 1;
      try {
        await capture(page, route, `${i}-${slug}`);
      } catch (err) {
        console.error(`  ${route} FAILED: ${err.message?.slice(0, 200)}`);
      }
    }
  } finally {
    await context.close();
    await browser.close();
  }

  console.log('');
  console.log(`Done. ${ROUTES.length} screenshots → ${OUT_DIR}`);
}

main().catch((err) => {
  console.error('FATAL:', err.message);
  process.exit(1);
});
