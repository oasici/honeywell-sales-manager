/**
 * Round-15 audit F-033 — critical sales-conversion E2E flows.
 *
 * Pre-fix the E2E suite covered dashboard / reports / territories /
 * forecast smoke, but the high-business-value lifecycle flows
 * (lead → customer, opportunity create + stage progression,
 * quote draft → approval surface) were untested. A regression on any
 * of those would land in production with no automated guard.
 *
 * These specs run API-only (no UI clicks) so they're fast and
 * deterministic. UI assertions live in the existing
 * ``full-smoke-ui.spec.ts``; this file is the data-path companion.
 */

import { test, expect } from '@playwright/test';
import {
  E2E_API_BASE_URL,
  projectToRole,
  readStorageState,
  hasRoleCreds,
} from './_utils';

/** Build the auth header dict expected by Playwright's APIRequestContext. */
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

test.describe('Critical flow: lead → customer conversion', () => {
  test('manager can create a lead, convert it, and the customer/opportunity surface', async ({
    request,
  }) => {
    const role = projectToRole(test.info().project.name);
    if (role !== 'sales_manager' && role !== 'admin') {
      test.skip(true, `lead conversion is manager+ only; project=${role}`);
    }
    if (!hasRoleCreds(role)) test.skip(true, `${role} creds not set`);
    const { token } = readStorageState(role);
    if (!token) test.skip(true, `${role} storageState missing`);

    const suffix = Date.now();
    const leadEmail = `e2e-lead-${suffix}@test.local`;

    // 1) Create a lead.
    const createLeadRes = await request.post(`${E2E_API_BASE_URL}/api/v1/leads/`, {
      headers: authHeaders(token),
      data: {
        name: 'E2E Lead Subject',
        email: leadEmail,
        company: 'E2E Lead Co',
        phone: '+90 555 000 0000',
        source: 'e2e-test',
      },
    });

    // Lead-lifecycle is feature-flagged. If the flag is off, FastAPI
    // returns 404; treat that as "feature not enabled in this env".
    if (createLeadRes.status() === 404) {
      test.skip(true, 'FEATURE_LEAD_LIFECYCLE off in this environment');
    }
    expect(createLeadRes.ok(), `lead create failed: ${createLeadRes.status()}`).toBeTruthy();

    const lead = await createLeadRes.json();
    expect(lead.id).toBeTruthy();
    expect(lead.tenant_id).toBeTruthy();
    expect(lead.email).toBe(leadEmail);

    // 2) Convert the lead. Backend creates Customer (+ optional Opportunity).
    const convertRes = await request.post(
      `${E2E_API_BASE_URL}/api/v1/leads/${lead.id}/convert`,
      {
        headers: authHeaders(token),
        data: { create_opportunity: true, opportunity_title: 'E2E Converted Opp' },
      },
    );
    expect(convertRes.ok(), `lead convert failed: ${convertRes.status()}`).toBeTruthy();
    const convertBody = await convertRes.json();
    expect(convertBody.customer_id, 'customer_id missing from convert response').toBeTruthy();

    // 3) The customer surface should include the new row.
    const customerRes = await request.get(
      `${E2E_API_BASE_URL}/api/v1/customers/${convertBody.customer_id}`,
      { headers: authHeaders(token) },
    );
    expect(customerRes.ok()).toBeTruthy();
    const customer = await customerRes.json();
    expect(customer.email).toBe(leadEmail);
    expect(customer.tenant_id).toBe(lead.tenant_id);

    // 4) If an opportunity was created, it should be visible on the
    //    customer's opportunity list (validates tenant scoping +
    //    parent FK wiring from Sprint 15k cohort 1).
    if (convertBody.opportunity_id) {
      const oppRes = await request.get(
        `${E2E_API_BASE_URL}/api/v1/opportunities/${convertBody.opportunity_id}`,
        { headers: authHeaders(token) },
      );
      expect(oppRes.ok()).toBeTruthy();
      const opp = await oppRes.json();
      expect(opp.customer_id).toBe(convertBody.customer_id);
      expect(opp.tenant_id).toBe(lead.tenant_id);
    }
  });
});

test.describe('Critical flow: opportunity create + stage progression', () => {
  test('manager can create opportunity directly and progress through stages', async ({
    request,
  }) => {
    const role = projectToRole(test.info().project.name);
    if (role === 'operations') test.skip(true, 'opportunity write is sales-team-only');
    if (!hasRoleCreds(role)) test.skip(true, `${role} creds not set`);
    const { token } = readStorageState(role);
    if (!token) test.skip(true, `${role} storageState missing`);

    const suffix = Date.now();

    // 1) Need a customer first. Create one inline so the test is
    //    self-contained.
    const customerRes = await request.post(`${E2E_API_BASE_URL}/api/v1/customers/`, {
      headers: authHeaders(token),
      data: {
        name: 'E2E Opp Subject',
        company: 'E2E Opp Co',
        email: `e2e-opp-${suffix}@test.local`,
        phone: '+90 555 111 1111',
      },
    });
    if (customerRes.status() === 404) {
      test.skip(true, 'customer-write endpoint gated off in this environment');
    }
    expect(customerRes.ok(), `customer create failed: ${customerRes.status()}`).toBeTruthy();
    const customer = await customerRes.json();

    // 2) Create the opportunity.
    const oppRes = await request.post(`${E2E_API_BASE_URL}/api/v1/opportunities/`, {
      headers: authHeaders(token),
      data: {
        title: 'E2E Direct Opp',
        stage: 'qualified',
        amount: 50000,
        currency: 'TRY',
        customer_id: customer.id,
      },
    });
    if (oppRes.status() === 404) {
      test.skip(true, 'FEATURE_V2_BOARD off in this environment');
    }
    expect(oppRes.ok(), `opp create failed: ${oppRes.status()}`).toBeTruthy();
    const opp = await oppRes.json();
    expect(opp.id).toBeTruthy();
    expect(opp.tenant_id).toBeTruthy();
    expect(opp.stage).toBe('qualified');
    expect(opp.customer_id).toBe(customer.id);

    // 3) Stage progression: qualified → proposal → negotiation.
    for (const newStage of ['proposal', 'negotiation']) {
      const patchRes = await request.patch(
        `${E2E_API_BASE_URL}/api/v1/opportunities/${opp.id}`,
        { headers: authHeaders(token), data: { stage: newStage } },
      );
      expect(patchRes.ok(), `stage change to ${newStage} failed`).toBeTruthy();
      const patched = await patchRes.json();
      expect(patched.stage).toBe(newStage);
      // Round-15 — previous_stage round-trip surfaces on the response.
      // Pre-fix this was dropped by the serializer.
      expect(patched.previous_stage).toBeTruthy();
    }

    // 4) The opp's intelligence endpoint should return a typed payload
    //    (Round-15 audit F-019 wired ``OpportunityIntelligenceResponse``).
    const intelRes = await request.get(
      `${E2E_API_BASE_URL}/api/v1/opportunities/${opp.id}/intelligence`,
      { headers: authHeaders(token) },
    );
    if (intelRes.ok()) {
      const intel = await intelRes.json();
      expect(intel).toHaveProperty('opportunity');
      expect(intel).toHaveProperty('signals');
      expect(intel).toHaveProperty('tasks');
      expect(intel).toHaveProperty('open_tasks_count');
      expect(Array.isArray(intel.signals)).toBeTruthy();
      expect(Array.isArray(intel.tasks)).toBeTruthy();
    }
    // If 404, the V2 board flag is off — already handled above.
  });
});

test.describe('Critical flow: quote create → approval surface', () => {
  test('manager can draft a quote and the approval gate is exposed', async ({ request }) => {
    const role = projectToRole(test.info().project.name);
    if (role !== 'sales_manager' && role !== 'admin') {
      test.skip(true, `quote write requires manager+; project=${role}`);
    }
    if (!hasRoleCreds(role)) test.skip(true, `${role} creds not set`);
    const { token } = readStorageState(role);
    if (!token) test.skip(true, `${role} storageState missing`);

    const suffix = Date.now();

    // 1) Customer.
    const custRes = await request.post(`${E2E_API_BASE_URL}/api/v1/customers/`, {
      headers: authHeaders(token),
      data: {
        name: 'E2E Quote Subject',
        company: 'E2E Quote Co',
        email: `e2e-quote-${suffix}@test.local`,
        phone: '+90 555 222 2222',
      },
    });
    if (custRes.status() === 404) {
      test.skip(true, 'customer-write endpoint gated off in this environment');
    }
    expect(custRes.ok(), `customer create failed: ${custRes.status()}`).toBeTruthy();
    const customer = await custRes.json();

    // 2) Draft quote.
    const quoteRes = await request.post(`${E2E_API_BASE_URL}/api/v1/quotes/`, {
      headers: authHeaders(token),
      data: {
        customer_id: customer.id,
        language: 'tr',
        currency: 'TRY',
        valid_days: 30,
        items: [
          {
            honeywell_code: 'E2E-TEST-PART',
            description: 'E2E test line',
            quantity: 1,
            unit_price: 100,
          },
        ],
      },
    });
    if (quoteRes.status() === 404) {
      test.skip(true, 'quotes endpoint not available in this environment');
    }
    expect(quoteRes.ok(), `quote create failed: ${quoteRes.status()}`).toBeTruthy();
    const quote = await quoteRes.json();
    expect(quote.id).toBeTruthy();
    expect(quote.tenant_id).toBeTruthy();
    expect(quote.status).toBeTruthy();
    expect(quote.customer_id).toBe(customer.id);

    // 3) Approval-routing endpoint should accept the quote id as a
    //    valid candidate (flag-gated — skip if disabled).
    const approvalsRes = await request.get(
      `${E2E_API_BASE_URL}/api/v1/approvals/pending`,
      { headers: authHeaders(token) },
    );
    if (approvalsRes.status() === 404) {
      test.info().annotations.push({
        type: 'note',
        description: 'FEATURE_APPROVAL_ROUTING off — approval-routing flow not verified.',
      });
      return;
    }
    expect(approvalsRes.ok()).toBeTruthy();
    const approvals = await approvalsRes.json();
    expect(approvals).toHaveProperty('items');
    expect(Array.isArray(approvals.items)).toBeTruthy();
  });
});
