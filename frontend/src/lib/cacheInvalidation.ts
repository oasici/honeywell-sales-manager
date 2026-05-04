/**
 * Cross-cutting cache invalidation helpers (R4-CACHE-101..112).
 *
 * Round-4 audit found 12 sites where a mutation succeeds and the
 * related TanStack Query caches go stale (kanban after stage change,
 * list after lead convert, contracts after invoice paid, etc).
 * Round-3 deferred this; round-4 enumerated each site and recommended
 * authoring a single helper module so point fixes don't rot.
 *
 * Each function takes the QueryClient + the key fields its server
 * effect touches (opportunity id, customer id, etc) and invalidates
 * the canonical query keys used elsewhere in the app. Add a new key
 * to one of these helpers when a feature ships a new query that
 * depends on the same server state.
 */
import type { QueryClient } from '@tanstack/react-query';

/**
 * After any mutation that changes an opportunity's stage / amount /
 * close_date / score / forecast_category. Invalidates the detail
 * query, the kanban + list, every AI/intelligence card keyed on the
 * opportunity id, and the cockpit + dashboard rollups.
 */
export function onOpportunityChanged(qc: QueryClient, opportunityId: number): void {
  qc.invalidateQueries({ queryKey: ['opportunity', opportunityId] });
  qc.invalidateQueries({ queryKey: ['opportunities'] });
  qc.invalidateQueries({ queryKey: ['board'] });
  qc.invalidateQueries({ queryKey: ['kanban'] });
  qc.invalidateQueries({ queryKey: ['opportunity-timeline', opportunityId] });
  qc.invalidateQueries({ queryKey: ['opportunity-intelligence', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-opp-summary', opportunityId] });
  qc.invalidateQueries({ queryKey: ['v4-opp-features-latest', opportunityId] });
  qc.invalidateQueries({ queryKey: ['decision-gaps', opportunityId] });
  qc.invalidateQueries({ queryKey: ['benchmarks-gap', opportunityId] });
  qc.invalidateQueries({ queryKey: ['forecast-adjustments', opportunityId] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
}

/**
 * After any mutation that changes a customer's profile / enrichment /
 * pin state / hierarchy. Invalidates customer detail, list, search,
 * Account 360, intelligence cards, and the high-intent pin list.
 */
export function onCustomerChanged(qc: QueryClient, customerId: number): void {
  qc.invalidateQueries({ queryKey: ['customer', customerId] });
  qc.invalidateQueries({ queryKey: ['customers'] });
  qc.invalidateQueries({ queryKey: ['customer-opportunities', customerId] });
  qc.invalidateQueries({ queryKey: ['account-360', customerId] });
  qc.invalidateQueries({ queryKey: ['customer-intelligence', customerId] });
  qc.invalidateQueries({ queryKey: ['team-members', customerId] });
  qc.invalidateQueries({ queryKey: ['high-intent-accounts'] });
}

/**
 * After lead.convert (creates Customer + optional Opportunity, marks
 * Lead converted). Invalidates leads list (row should disappear from
 * the qualified queue), customers/opportunities lists, campaign
 * member rollups, and the cockpit pipeline tile.
 */
export function onLeadConverted(qc: QueryClient, leadId: number): void {
  qc.invalidateQueries({ queryKey: ['lead', leadId] });
  qc.invalidateQueries({ queryKey: ['leads'] });
  qc.invalidateQueries({ queryKey: ['customers'] });
  qc.invalidateQueries({ queryKey: ['opportunities'] });
  qc.invalidateQueries({ queryKey: ['campaign-members'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
}

/** After lead.score_changed mutation (rescore endpoint). */
export function onLeadScoreChanged(qc: QueryClient, leadId: number): void {
  qc.invalidateQueries({ queryKey: ['lead', leadId] });
  qc.invalidateQueries({ queryKey: ['leads'] });
  qc.invalidateQueries({ queryKey: ['notifications'] });
}

/**
 * After quote.approve / quote.send. Updates the quote detail and
 * the list, fires a notification (so the badge polls less laggy),
 * and updates the linked opportunity timeline + activity summary.
 */
export function onQuoteStatusChanged(
  qc: QueryClient,
  quoteId: number,
  opportunityId?: number | null,
): void {
  qc.invalidateQueries({ queryKey: ['quote', quoteId] });
  qc.invalidateQueries({ queryKey: ['quotes'] });
  qc.invalidateQueries({ queryKey: ['notifications'] });
  if (opportunityId) {
    qc.invalidateQueries({ queryKey: ['opportunity-timeline', opportunityId] });
    qc.invalidateQueries({ queryKey: ['activity-summary', opportunityId] });
  }
}

/**
 * After invoice.status changes (especially → paid). The bus event
 * propagates to contract.actual_revenue and rev-rec rollups, so the
 * contract detail + list + rev-rec schedules + cockpit need a refresh.
 */
export function onInvoiceStatusChanged(
  qc: QueryClient,
  invoiceId: number,
  contractId?: number | null,
  opportunityId?: number | null,
): void {
  qc.invalidateQueries({ queryKey: ['invoice', invoiceId] });
  qc.invalidateQueries({ queryKey: ['invoices'] });
  qc.invalidateQueries({ queryKey: ['rev-rec-schedules'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  if (contractId) {
    qc.invalidateQueries({ queryKey: ['contract', contractId] });
    qc.invalidateQueries({ queryKey: ['contracts'] });
  }
  if (opportunityId) {
    qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
  }
}

/** After contract.activate / amend. */
export function onContractChanged(qc: QueryClient, contractId: number): void {
  qc.invalidateQueries({ queryKey: ['contract', contractId] });
  qc.invalidateQueries({ queryKey: ['contracts'] });
}

/**
 * After a merge — touches every list. Use a full sweep because
 * merges are rare and the loser id is referenced from many caches
 * we don't want to enumerate.
 */
export function onRecordsMerged(qc: QueryClient): void {
  qc.invalidateQueries();
}

/**
 * After a stakeholder add/delete on an opportunity. The stakeholder
 * count is a feature input to deal-risk / decision-gap / benchmark
 * cards, so we invalidate those too.
 */
export function onStakeholderChanged(qc: QueryClient, opportunityId: number): void {
  qc.invalidateQueries({ queryKey: ['stakeholders', opportunityId] });
  qc.invalidateQueries({ queryKey: ['stakeholder-alerts', opportunityId] });
  qc.invalidateQueries({ queryKey: ['decision-gaps', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
  qc.invalidateQueries({ queryKey: ['benchmarks-gap', opportunityId] });
}

/**
 * After QuickActivityModal logs an activity. Activity propagates to
 * customer.last_activity_at, opportunity rotting counters, and
 * revenue_signal stream — all of which the kanban card and cockpit
 * surface.
 */
export function onActivityLogged(
  qc: QueryClient,
  opportunityId: number | null,
  customerId?: number | null,
): void {
  qc.invalidateQueries({ queryKey: ['activities'] });
  if (opportunityId) {
    qc.invalidateQueries({ queryKey: ['opportunity-timeline', opportunityId] });
    qc.invalidateQueries({ queryKey: ['opportunity', opportunityId] });
    qc.invalidateQueries({ queryKey: ['board'] });
    qc.invalidateQueries({ queryKey: ['kanban'] });
  }
  if (customerId) {
    qc.invalidateQueries({ queryKey: ['customer', customerId] });
  }
  qc.invalidateQueries({ queryKey: ['cockpit'] });
}
