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
  // Round-8 R8-CACHE-4 — OpportunitiesHomePage uses its own list key.
  qc.invalidateQueries({ queryKey: ['opportunities-home'] });
  qc.invalidateQueries({ queryKey: ['board'] });
  qc.invalidateQueries({ queryKey: ['kanban'] });
  qc.invalidateQueries({ queryKey: ['opportunity-timeline', opportunityId] });
  qc.invalidateQueries({ queryKey: ['opportunity-intelligence', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-opp-summary', opportunityId] });
  // Round-15 F-025 — AI ``summarize-changes`` for opps; tuple key
  // includes a ``days`` window so invalidate by predicate.
  qc.invalidateQueries({
    predicate: (q) =>
      Array.isArray(q.queryKey) &&
      q.queryKey[0] === 'ai-opp-changes' &&
      q.queryKey[1] === opportunityId,
  });
  qc.invalidateQueries({ queryKey: ['activity-summary', opportunityId] });
  qc.invalidateQueries({ queryKey: ['v4-opp-features-latest', opportunityId] });
  qc.invalidateQueries({ queryKey: ['decision-gaps', opportunityId] });
  qc.invalidateQueries({ queryKey: ['decision-graph', opportunityId] });
  qc.invalidateQueries({ queryKey: ['benchmarks-gap', opportunityId] });
  qc.invalidateQueries({ queryKey: ['forecast-adjustments', opportunityId] });
  // Round-8 R8-CACHE-4 — week-over-week pipeline rollup keyed off active deals.
  qc.invalidateQueries({ queryKey: ['forecast-wow'] });
  // Round-8 — NBA tray reads task list keyed by opportunity id.
  qc.invalidateQueries({ queryKey: ['nba', opportunityId] });
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
  // Round-15 F-025 — the AI ``summarize-changes`` widget caches under
  // a (customerId, days) tuple. Include all variants by predicate.
  qc.invalidateQueries({
    predicate: (q) =>
      Array.isArray(q.queryKey) &&
      q.queryKey[0] === 'ai-customer-changes' &&
      q.queryKey[1] === customerId,
  });
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
 * Round-15 Sprint 15g cohort 6 — generic lead field update.
 *
 * Lead detail edits (status / owner / company / etc.) need to refresh
 * the detail card AND the list page so the row reflects the change
 * without a manual reload.
 */
export function onLeadChanged(qc: QueryClient, leadId: number): void {
  qc.invalidateQueries({ queryKey: ['lead', leadId] });
  qc.invalidateQueries({ queryKey: ['leads'] });
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

/**
 * R7-CACHE-1 — Lead created from list / web-lead form / CSV import.
 * Pre-fix LeadListPage.create only invalidated `['leads']`, missing
 * the dashboard funnel + cockpit lead-source rollup that read from
 * the same writes.
 */
export function onLeadCreated(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['leads'] });
  qc.invalidateQueries({ queryKey: ['lead-analytics'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['notifications'] });
}

/**
 * R7-CACHE-1 — Customer created. Touches the customer list, the
 * high-intent pin list (new customer with high intent score lands
 * directly), and the dashboard customer-count tile.
 */
export function onCustomerCreated(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['customers'] });
  qc.invalidateQueries({ queryKey: ['high-intent-accounts'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  qc.invalidateQueries({ queryKey: ['notifications'] });
}

/**
 * R7-CACHE-1 — Email parsed / re-parsed / reviewed. List view, the
 * email's detail, and the matches sub-query all need to refresh.
 */
export function onEmailChanged(qc: QueryClient, emailId: number | null): void {
  qc.invalidateQueries({ queryKey: ['emails'] });
  if (emailId) {
    qc.invalidateQueries({ queryKey: ['email', emailId] });
    qc.invalidateQueries({ queryKey: ['email-matches', emailId] });
  }
  qc.invalidateQueries({ queryKey: ['notifications'] });
}

/**
 * R7-CACHE-1 — Invoice created (especially via from-quote). Pre-fix
 * the SPA only invalidated `['invoices']`. Customer detail's revenue
 * tile + cockpit cash-flow rollup also read from invoice writes.
 */
export function onInvoiceCreated(qc: QueryClient, customerId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['invoices'] });
  qc.invalidateQueries({ queryKey: ['rev-rec-schedules'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  if (customerId) {
    qc.invalidateQueries({ queryKey: ['customer', customerId] });
    qc.invalidateQueries({ queryKey: ['account-360', customerId] });
  }
}

/**
 * R7-CACHE-1 — Subscription created or updated. Invalidates list,
 * the renewals queue (a new sub may show up there shortly), and the
 * MRR dashboard.
 */
export function onSubscriptionChanged(qc: QueryClient, subscriptionId: number | null): void {
  qc.invalidateQueries({ queryKey: ['subscriptions'] });
  if (subscriptionId) {
    qc.invalidateQueries({ queryKey: ['subscriptions', String(subscriptionId)] });
  }
}

/**
 * R7-CACHE-1 — Campaign created/updated. Invalidates campaign list,
 * the campaign's detail (members + ROI), and the dashboard tile.
 */
export function onCampaignChanged(qc: QueryClient, campaignId: number | null): void {
  qc.invalidateQueries({ queryKey: ['campaigns'] });
  if (campaignId) {
    qc.invalidateQueries({ queryKey: ['campaign', campaignId] });
    qc.invalidateQueries({ queryKey: ['campaign-roi', campaignId] });
    qc.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
  }
  qc.invalidateQueries({ queryKey: ['dashboard'] });
}

/**
 * Round-8 — AI attribute definition created/toggled/updated. Invalidates
 * the definition list (filtered + unfiltered variants via prefix match).
 */
export function onAiAttributeDefinitionChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['ai-attributes', 'definitions'] });
}

/**
 * Round-8 — AI attribute value generated/updated for a given entity.
 * Invalidates the values list keyed by ``(entity_type, entity_id)``.
 */
export function onAiAttributeValueChanged(
  qc: QueryClient,
  entityType: string,
  entityId: number,
): void {
  qc.invalidateQueries({ queryKey: ['ai-attributes', 'values', entityType, entityId] });
}

/**
 * Round-8 — Decision graph mutated (initialize/patch). The graph itself
 * re-renders via the dedicated key; downstream cards consuming process
 * completion (gaps, deal-risk) also refresh.
 */
export function onDecisionGraphChanged(qc: QueryClient, opportunityId: number): void {
  qc.invalidateQueries({ queryKey: ['decision-graph', opportunityId] });
  qc.invalidateQueries({ queryKey: ['decision-gaps', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
  qc.invalidateQueries({ queryKey: ['opportunity-intelligence', opportunityId] });
}

/**
 * Round-8 — Relationship graph rebuilt for an opportunity. Cascades into
 * coverage-driven cards (decision gaps, stakeholder alerts, deal risk).
 */
export function onRelationshipsRebuilt(qc: QueryClient, opportunityId: number): void {
  qc.invalidateQueries({ queryKey: ['relationship-score', 'opportunity', opportunityId] });
  qc.invalidateQueries({ queryKey: ['relationship-strongest', 'opportunity', opportunityId] });
  qc.invalidateQueries({ queryKey: ['relationship-edges', 'opportunity', opportunityId] });
  qc.invalidateQueries({ queryKey: ['decision-gaps', opportunityId] });
  qc.invalidateQueries({ queryKey: ['stakeholder-alerts', opportunityId] });
  qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
}

// ── Round-14 Sprint 14c — additional helpers for the cohorts the R14 ──
// audit flagged as drifting (10× cockpit, 7× compliance, 5× each on
// subscriptions/playbooks/emails/ai-tasks ad-hoc invalidations). These
// helpers let feature code stop reaching into invalidateQueries
// directly; the audit's R14-CACHE-1 fix lands here, and a follow-up
// ESLint rule will warn on raw invalidateQueries() calls in features/.

/**
 * Round-14 — Cockpit signal resolved / dismissed. Touches the cockpit
 * rollup, the originating opportunity card, and the dashboard.
 */
export function onCockpitSignalChanged(qc: QueryClient, opportunityId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  if (opportunityId) {
    qc.invalidateQueries({ queryKey: ['opportunity', opportunityId] });
    qc.invalidateQueries({ queryKey: ['ai-deal-risk', opportunityId] });
  }
}

/**
 * Round-14 — Compliance state mutated (consent toggled, retention
 * applied, breach acknowledged). Invalidates the compliance dashboard,
 * audit log, and the affected customer's detail.
 */
export function onComplianceChanged(qc: QueryClient, customerId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['compliance'] });
  qc.invalidateQueries({ queryKey: ['audit-log'] });
  if (customerId) {
    qc.invalidateQueries({ queryKey: ['customer', customerId] });
  }
}

/** Round-14 — Email template CRUD. Templates feed the composer + sequence steps. */
export function onEmailTemplateChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['email-templates'] });
  qc.invalidateQueries({ queryKey: ['email-template-variables'] });
}

/** Round-14 — Playbook CRUD or execution state change. */
export function onPlaybookChanged(qc: QueryClient, playbookId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['playbooks'] });
  qc.invalidateQueries({ queryKey: ['playbook-executions'] });
  qc.invalidateQueries({ queryKey: ['playbook-analytics'] });
  if (playbookId) {
    qc.invalidateQueries({ queryKey: ['playbook', playbookId] });
  }
}

/** Round-14 — Webhook subscription created/updated/tested. */
export function onWebhookChanged(qc: QueryClient, webhookId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['webhooks'] });
  if (webhookId) {
    qc.invalidateQueries({ queryKey: ['webhook-deliveries', webhookId] });
  }
}

/** Round-14 — Sequence definition or enrollment changed.
 *
 * Round-15 Sprint 15g — expanded to include sequence-performance +
 * cockpit-prefixed sequence rollups. SequencesPage previously duplicated
 * the same 5-key invalidation inline across 3 mutations (15 sites);
 * folding them into one helper retires the duplication and keeps the
 * fan-out coherent for any new sequence-keyed surface.
 */
export function onSequenceChanged(qc: QueryClient, opportunityId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['sequences'] });
  qc.invalidateQueries({ queryKey: ['sequence-enrollments'] });
  qc.invalidateQueries({ queryKey: ['sequence-analytics'] });
  qc.invalidateQueries({ queryKey: ['sequence-performance'] });
  qc.invalidateQueries({ queryKey: ['cockpit', 'sequence-analytics'] });
  qc.invalidateQueries({ queryKey: ['cockpit', 'sequence-performance'] });
  if (opportunityId) {
    qc.invalidateQueries({ queryKey: ['opportunity-intelligence', opportunityId] });
  }
}

/** Round-14 — Territory CRUD or rules / assignment edited. */
export function onTerritoryChanged(qc: QueryClient, territoryId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['territories-tree'] });
  if (territoryId) {
    qc.invalidateQueries({ queryKey: ['territory-detail', territoryId] });
  }
}

/** Round-14 — Approval rule CRUD. */
export function onApprovalRuleChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['approval-rules'] });
  qc.invalidateQueries({ queryKey: ['approvals'] });
}

/** Round-14 — Revenue schedule entry recognized / refunded.
 *
 * Round-15 Sprint 15g cohort 5 — also invalidates the
 * ``['revenue-dashboard']`` rollup that RevenueRecognitionPage
 * surfaces. Pre-fix, the page redundantly invalidated both keys
 * inline; folding it here keeps the fan-out coherent.
 */
export function onRevenueScheduleChanged(qc: QueryClient, contractId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['revenue-schedules'] });
  qc.invalidateQueries({ queryKey: ['revenue-dashboard'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  if (contractId) {
    qc.invalidateQueries({ queryKey: ['contract', contractId] });
  }
}

/** Round-14 — Pipeline / stage-config edited by an admin. */
export function onPipelineConfigChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['pipelines'] });
  qc.invalidateQueries({ queryKey: ['stage-configs'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['forecast-hybrid'] });
}

/**
 * Round-15 Sprint 15g cohort 4 — AI task CRUD or status change.
 *
 * AI-generated tasks surface on the AI-Tasks admin page and on each
 * opportunity's NBA tray (next-best-action). A mutation that touches
 * the task should invalidate both views plus the notifications badge.
 */
export function onAiTaskChanged(qc: QueryClient, opportunityId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['ai-tasks'] });
  if (opportunityId) {
    qc.invalidateQueries({ queryKey: ['nba', opportunityId] });
  }
  qc.invalidateQueries({ queryKey: ['notifications'] });
}

/**
 * Round-15 Sprint 15g cohort 5 — Custom dashboard CRUD or widget edit.
 *
 * Dashboards built via DashboardBuilder render on the list page and
 * a viewer page; both consume the same ``['dashboards']`` query, and
 * widget edits affect the executed result keyed by dashboard id.
 */
export function onDashboardChanged(qc: QueryClient, dashboardId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['dashboards'] });
  if (dashboardId) {
    qc.invalidateQueries({ queryKey: ['dashboard-execute', dashboardId] });
  }
}

/**
 * Round-15 Sprint 15g cohort 7 — User CRUD (admin → user mgmt page).
 *
 * UserManagementPage previously duplicated ``['users']`` invalidation
 * inline across 2 mutations (create + update). Wiring it through the
 * registry retires the duplication and is a single point where new
 * user-keyed surfaces (role audit, audit-log filter) can be added.
 */
export function onUserChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['users'] });
}

/**
 * Round-15 Sprint 15g cohort 7 — Sharing rule CRUD.
 *
 * SharingRulesSection had inline invalidations on the same key from
 * 2 mutations. Folded into one helper for parity with the other
 * settings-page registries (territory, approval-rule, pipeline-config).
 */
export function onSharingRuleChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['sharing-rules'] });
}

/**
 * Round-15 Sprint 15g cohort 7 — Account team member added / removed.
 *
 * AccountTeamPanel invalidated the per-customer team-members key
 * inline. The team-member count is also a feature input to
 * ``customer-intelligence`` and ``account-360``, so folding here
 * lets us pick up those rollups in a single point if the panel grows.
 */
export function onTeamMemberChanged(qc: QueryClient, customerId: number): void {
  qc.invalidateQueries({ queryKey: ['team-members', customerId] });
  qc.invalidateQueries({ queryKey: ['account-360', customerId] });
}

/**
 * Round-15 Sprint 15g cohort 7 — Part CRUD (parts catalog admin).
 *
 * PartsPage create / update / delete invalidated ``['parts']`` AND
 * ``['parts-categories']`` inline; folded into one helper so any
 * future parts-keyed surface (parts-intel summary, BOM picker) is
 * captured here rather than at every call site.
 */
export function onPartChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['parts'] });
  qc.invalidateQueries({ queryKey: ['parts-categories'] });
}

/**
 * Round-15 Sprint 15g cohort 7 — Pricing tier or customer-pricing edit.
 *
 * PricingAdminPage had 5 inline invalidations across 3 distinct keys
 * (``['pricing-tiers', priceEntryId]``, ``['customer-pricing', cid]``,
 * ``['parts', 'all']``). The helper takes both ids so the same call
 * covers tier edits and customer-specific overrides, plus a single
 * place to also refresh the parts catalog (price changes propagate
 * to the price column shown in PartsPage).
 */
export function onPricingChanged(
  qc: QueryClient,
  priceEntryId?: number | null,
  customerId?: number | null,
): void {
  qc.invalidateQueries({ queryKey: ['pricing-tiers'] });
  qc.invalidateQueries({ queryKey: ['parts', 'all'] });
  if (priceEntryId) {
    qc.invalidateQueries({ queryKey: ['pricing-tiers', priceEntryId] });
  }
  if (customerId) {
    qc.invalidateQueries({ queryKey: ['customer-pricing', customerId] });
  }
}

/**
 * Round-15 Sprint 15g cohort 7 — Integration connector connected /
 * disconnected / token refreshed.
 *
 * IntegrationsPage manages calendar + e-sign + email connectors. Each
 * connector previously invalidated its own narrow key inline. Helper
 * accepts the connector kind so the same registry covers all three
 * without leaking implementation detail into the page.
 */
export function onIntegrationChanged(
  qc: QueryClient,
  kind?: 'calendar' | 'esign' | 'email' | null,
): void {
  qc.invalidateQueries({ queryKey: ['integrations'] });
  if (kind) {
    qc.invalidateQueries({ queryKey: ['integrations', kind] });
  }
}

/**
 * Round-15 Sprint 15g cohort 8 — Tenant-level settings touched.
 *
 * SettingsPage saves a single ``tenant_settings`` row that gates most
 * organization-wide preferences (currency, locale, feature toggles).
 * Helper exists so future settings-keyed surfaces (e.g. a settings
 * audit panel) can fan out from one place.
 */
export function onSettingsChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['settings'] });
}

/**
 * Round-15 Sprint 15g cohort 8 — Email credential (SMTP / IMAP / OAuth)
 * connected, rotated, or deleted from the per-user inbox settings.
 */
export function onEmailCredentialChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['email-credentials'] });
  qc.invalidateQueries({ queryKey: ['integrations', 'email'] });
}

/**
 * Round-15 Sprint 15g cohort 8 — Stage-config edit (kanban column,
 * probability, sla). Distinct from generic pipeline-config because the
 * stage-config dialog lives under SettingsPage and edits affect the
 * board + every per-stage rollup.
 */
export function onStageConfigChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['stage-config'] });
  qc.invalidateQueries({ queryKey: ['stage-configs'] });
  qc.invalidateQueries({ queryKey: ['pipelines'] });
  qc.invalidateQueries({ queryKey: ['board'] });
  qc.invalidateQueries({ queryKey: ['kanban'] });
}

/**
 * Round-15 Sprint 15g cohort 8 — Meeting link CRUD. Used by the
 * Schedule a Meeting modal across opportunities; SettingsPage manages
 * the underlying templates.
 */
export function onMeetingLinkChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['meeting-links'] });
}

/**
 * Round-15 Sprint 15g cohort 8 — Agent chat session created /
 * renamed / archived. AgentChatPage groups conversations by session
 * and the session list is the primary navigation.
 */
export function onChatSessionChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['chat-sessions'] });
}

/**
 * Round-15 Sprint 15g cohort 8 — Agent chat message posted /
 * regenerated. The message list query is keyed by session id.
 */
export function onChatMessageChanged(qc: QueryClient, sessionId: number | string | null): void {
  if (sessionId != null) {
    qc.invalidateQueries({ queryKey: ['chat-messages-agent', sessionId] });
  }
}

/**
 * Round-15 Sprint 15g cohort 8 — Admin workflow rule CRUD.
 *
 * WorkflowRulesPage replicates the helper-shape pattern from
 * ``onApprovalRuleChanged`` — list-only fan-out since the rule
 * detail is rendered inline within the row.
 */
export function onWorkflowRuleChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['workflowRules'] });
}

/**
 * Round-15 Sprint 15g cohort 8 — AI competitive intel refreshed
 * from the cockpit tile. Each tenant has a single rollup so the
 * helper is parameter-less.
 */
export function onAiCompetitiveIntelChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['ai-competitive-intel'] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
}

/**
 * Round-15 Sprint 15g cohort 9 — generic quote CRUD (save/edit body,
 * line-item edits) without the status fan-out.
 *
 * Distinct from ``onQuoteStatusChanged`` which also invalidates
 * notifications + opportunity timeline + activity-summary — none of
 * those rollups change when a draft quote's body is edited.
 */
export function onQuoteChanged(qc: QueryClient, quoteId?: number | null): void {
  qc.invalidateQueries({ queryKey: ['quotes'] });
  if (quoteId) {
    qc.invalidateQueries({ queryKey: ['quote', quoteId] });
  }
}

/**
 * Round-15 Sprint 15g cohort 9 — Comment posted / deleted on any
 * entity (opportunity / customer / quote / etc). Thread is keyed by
 * ``(entityType, entityId)``.
 */
export function onCommentChanged(qc: QueryClient, entityType: string, entityId: number): void {
  qc.invalidateQueries({ queryKey: ['comments', entityType, entityId] });
}

/**
 * Round-15 Sprint 15g cohort 9 — Custom field definition CRUD.
 *
 * Custom-field definitions are admin-configured and read by every
 * entity detail page that renders extra fields. Helper accepts the
 * entity_type so it can target the per-type query without flushing
 * unrelated definitions.
 */
export function onCustomFieldChanged(qc: QueryClient, entityType: string): void {
  qc.invalidateQueries({ queryKey: ['customFields', entityType] });
}

/**
 * Round-15 Sprint 15g cohort 9 — Field-level permission rule
 * (FieldPermissionsPage). Permission table is global; reload the
 * single ``['fieldPermissions']`` cache on each rule write.
 */
export function onFieldPermissionChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['fieldPermissions'] });
}

/**
 * Round-15 Sprint 15g cohort 9 — Product rule (quote line constraint)
 * created / toggled / deleted.
 */
export function onProductRuleChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['productRules'] });
}

/**
 * Round-15 Sprint 15g cohort 9 — Pending approval acted on
 * (approved / rejected). Reuses the ``onApprovalRuleChanged`` queue
 * key alongside the per-row detail.
 */
export function onApprovalActionTaken(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['approvals'] });
  qc.invalidateQueries({ queryKey: ['notifications'] });
}

/**
 * Round-15 Sprint 15g cohort 9 — Stakeholder graph mutated from the
 * opportunity buyer-relationship map. Same cache surface as
 * ``onStakeholderChanged`` but reachable from list-side callers
 * that don't pre-import the full registry.
 */
export function onStakeholderGraphChanged(qc: QueryClient, opportunityId: number): void {
  qc.invalidateQueries({ queryKey: ['stakeholders', opportunityId] });
  qc.invalidateQueries({ queryKey: ['stakeholder-alerts', opportunityId] });
}

/**
 * Round-15 Sprint 15g cohort 9 — Relationship metric refreshed for a
 * non-opportunity entity (currently used for customer-keyed and
 * lead-keyed cards in RelationshipPanel). Distinct from
 * ``onRelationshipsRebuilt`` which is opportunity-scoped and fans
 * out to gap / risk cards.
 */
export function onRelationshipMetricChanged(qc: QueryClient, kind: string, entityId: number): void {
  qc.invalidateQueries({ queryKey: ['relationship-score', kind, entityId] });
  qc.invalidateQueries({ queryKey: ['relationship-strongest', kind, entityId] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Deal room mutated (welcome edit,
 * mutual-action-plan update, share toggle). Each room is keyed by id;
 * the list view consumes ``['deal-rooms']``.
 */
export function onDealRoomChanged(qc: QueryClient, roomId: number | null): void {
  qc.invalidateQueries({ queryKey: ['deal-rooms'] });
  if (roomId) {
    qc.invalidateQueries({ queryKey: ['deal-room', roomId] });
  }
}

/**
 * Round-15 Sprint 15g cohort 10 — Engagement keyword pack CRUD.
 *
 * KeywordPacksPage lists the per-tenant keyword bundles used by
 * the email + transcript signal extractor.
 */
export function onKeywordPackChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['keyword-packs'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Engagement segment CRUD.
 * Segments are saved filter definitions consumed by transcript /
 * email matching rules.
 */
export function onSegmentChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['segments'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Transcript imported / re-tagged.
 * Currently a single list; helper exists so future transcript-keyed
 * cards (per-deal transcript chip) fan out from one place.
 */
export function onTranscriptChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['transcripts'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Saved report template CRUD.
 */
export function onSavedReportChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['report-templates'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Coaching plan CRUD.
 * Plan list lives under ``['coaching', 'plans']`` per the page
 * convention; helper centralizes that key.
 */
export function onCoachingPlanChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['coaching', 'plans'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Saved view CRUD (per-list quick
 * filter). PlanningStudioPage + list pages share the same key.
 */
export function onSavedViewChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['saved-views'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — Chat widget (buyer-facing) message
 * posted. Distinct key from the agent-side ``['chat-messages-agent', id]``
 * tracked by ``onChatMessageChanged``.
 */
export function onChatWidgetMessageChanged(
  qc: QueryClient,
  sessionId: number | string | null,
): void {
  if (sessionId != null) {
    qc.invalidateQueries({ queryKey: ['chat-messages', sessionId] });
  }
}

/**
 * Round-15 Sprint 15g cohort 10 — Forecast week-over-week rollup
 * manually recomputed from SalesAnalyticsPage. Narrow scope (no
 * cockpit fan-out) — the user is already on the analytics page.
 */
export function onForecastWowChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['forecast-wow'] });
}

/**
 * Round-15 Sprint 15g cohort 10 — High-intent pin list mutated from
 * the dedicated HighIntentAccountsPage. Narrower than
 * ``onCustomerChanged``'s full fan-out since the page only operates
 * on the pin list, not customer profile fields.
 */
export function onHighIntentChanged(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ['high-intent-accounts'] });
}

/**
 * Round-15 Sprint 15g cohort 11 — Forecast adjustment recorded on
 * an opportunity (commit / best-case override).
 *
 * Pre-fix OpportunityDetailPage enumerated all 4 keys inline per
 * R4-CACHE-110 comment. Helper centralizes the fan-out so any new
 * forecast-adjustment-keyed surface (e.g. a per-deal commit history
 * panel) is captured here, not at the call site.
 */
export function onForecastAdjustmentChanged(qc: QueryClient, opportunityId: number): void {
  qc.invalidateQueries({ queryKey: ['forecast-adjustments', opportunityId] });
  qc.invalidateQueries({ queryKey: ['cockpit'] });
  qc.invalidateQueries({ queryKey: ['dashboard'] });
  qc.invalidateQueries({ queryKey: ['forecast-wow'] });
}
