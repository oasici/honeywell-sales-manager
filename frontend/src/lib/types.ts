// ── User ──────────────────────────────────────────────
export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  email_setup_completed: boolean;
  created_at: string;
}

// ── Customer ─────────────────────────────────────────
export interface Customer {
  id: number;
  /** V8 multi-tenant boundary — round-tripped so the UI can verify isolation. */
  tenant_id?: number | null;
  name: string;
  company: string;
  email: string;
  phone: string;
  address: string;
  tax_id: string;
  preferred_lang: string;
  created_at: string;
  /** Owner — round-tripped by the API but missing from TS pre-audit (TS-3). */
  created_by?: number;
  /** Last-update timestamp — needed to render "updated X ago" labels. */
  updated_at?: string | null;
  quote_count?: number;
  total_quote_value?: number;
  industry?: string | null;
  employee_count?: number | null;
  annual_revenue?: string | null;
  website?: string | null;
  linkedin_url?: string | null;
  enriched_at?: string | null;
  /** Present on GET /customers/:id — current user's pin for high-intent list. */
  pinned?: boolean;
  /** Account hierarchy — parent account id when this is a child entity. */
  parent_id?: number | null;
  /** Territory FK; used by territory-scoped list filters. */
  territory_id?: number | null;
}

export interface CustomerIntelligenceOpportunityItem {
  id: number;
  title: string;
  stage: string;
  amount: number | null;
  currency: string;
  owner_id: number;
  close_date: string | null;
  updated_at: string | null;
  last_activity_at: string | null;
}

export interface CustomerIntelligenceSignalItem {
  id: number;
  opportunity_id: number;
  signal_type: string;
  severity: string;
  evidence: string | null;
  source_type: string | null;
  source_id: number | null;
  is_resolved: boolean;
  created_at: string | null;
}

export interface CustomerIntelligenceResponse {
  customer: Customer;
  opportunities: CustomerIntelligenceOpportunityItem[];
  open_tasks_count: number;
  signals: CustomerIntelligenceSignalItem[];
}

export interface Account360Enrichment {
  customer_id: number;
  currency: string;
  pipeline_open_amount: number;
  closed_won_revenue: number;
  active_deal_count: number;
  won_deal_count: number;
  lost_deal_count: number;
  total_deal_count: number;
  risk_index: number;
  engagement_score: number;
  computed_at: string | null;
  health_score: number | null;
  health_risk_level: string | null;
}

export interface Account360LastTouch {
  at: string | null;
  source: string;
  summary: string;
}

export interface Account360OpenDeal {
  id: number;
  title: string;
  stage: string;
  amount: number | null;
  currency: string;
  owner_id: number;
  updated_at: string | null;
}

export interface Account360RiskSummary {
  health_score: number | null;
  risk_level: string;
  risk_index: number | null;
  unresolved_high_signals: number;
  recommendations: string[];
}

export interface Account360TimelineItem {
  kind: string;
  occurred_at: string | null;
  opportunity_id: number | null;
  opportunity_title: string | null;
  event_type: string;
  entity_type: string | null;
  entity_id: number | null;
  description: string | null;
}

export interface Account360Response {
  customer_id: number;
  enrichment: Account360Enrichment;
  last_touch: Account360LastTouch;
  open_deals: Account360OpenDeal[];
  risk_summary: Account360RiskSummary;
  timeline: Account360TimelineItem[];
}

export interface AiMeetingPrepResponse {
  prep: string;
  customer_id: number;
}

export interface HighIntentAccountItem {
  customer_id: number;
  name: string;
  company: string | null;
  score: number;
  signals: string[];
  pinned: boolean;
}

export interface HighIntentListResponse {
  items: HighIntentAccountItem[];
  total: number;
}

// ── Email Request ────────────────────────────────────
export interface ParsedPart {
  part_code: string;
  part_description: string;
  quantity: number;
  urgency: string;
}

export interface ParsedData {
  language: string;
  customer_name: string;
  customer_company: string;
  parts: ParsedPart[];
  is_spare_part_request: boolean;
  category: string;
  confidence: number;
}

export interface EmailRequest {
  id: number;
  customer_id: number | null;
  opportunity_id?: number | null;
  message_id: string;
  from_address: string;
  subject: string;
  body_text: string;
  body_html: string;
  language: string;
  received_at: string;
  status: string;
  parsed_data: ParsedData | null;
  error_message: string | null;
  category: string | null;
  category_confidence: number | null;
  // Round-4 R4-FMT-1 — DB column is `bool | None`; backend returns
  // raw bool. The previous `string | null` was an outright type lie
  // (`email.price_sensitivity === 'high'` always evaluated false).
  price_sensitivity: boolean | null;
  review_status: string | null;
  assigned_to: number | null;
  reviewed_by: number | null;
  thread_id?: string | null;
  in_reply_to?: string | null;
  is_read: boolean;
  // AI triage outputs — populated by the email parsing pipeline.
  // ``priority`` drives inbox sorting/colouring, ``triage_reason``
  // is a one-line rationale, ``sentiment`` is a coarse bucket
  // (positive/neutral/negative) with an accompanying numeric score
  // [-1, 1]. ``data_classification`` flags KVKK-sensitive payloads.
  priority?: 'low' | 'normal' | 'high' | 'urgent' | null;
  triage_reason?: string | null;
  sentiment?: 'positive' | 'neutral' | 'negative' | null;
  sentiment_score?: number | null;
  data_classification?: 'public' | 'internal' | 'confidential' | 'restricted' | null;
  last_parsed_at: string | null;
  created_at: string;
}

// ── Spare Part ───────────────────────────────────────
export interface SparePart {
  id: number;
  honeywell_code: string;
  model_number?: string | null;
  info?: string | null;
  // Round-4 R4-NAME-1 — DB allows NULL on these text fields. Marking
  // non-null caused JSX like `name_tr.toUpperCase()` to crash on
  // imports without a Turkish name.
  name_en: string | null;
  name_tr: string | null;
  description_en: string | null;
  description_tr: string | null;
  category: string | null;
  subcategory: string | null;
  transfer_price?: number | null;
  supplier_price?: number | null;
  price_currency?: string | null;
  // Round-4 R4-CLOSE-2a/b — backend returns these but TS used to
  // drop them, so the AI matcher couldn't surface keyword hits.
  keywords_json?: string | null;
  aliases_json?: string | null;
  is_active: boolean;
  created_at: string;
}

// ── Price Entry ──────────────────────────────────────
export interface PriceEntry {
  id: number;
  spare_part_id: number;
  list_price: number;
  discount_pct: number;
  net_price: number;
  currency: string;
  valid_from: string;
  valid_until: string;
  price_list_version: string;
}

// ── Quote ────────────────────────────────────────────
// Mirrors backend QuoteStatus enum (app/models/enums.py).
export type QuoteStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'sent'
  | 'accepted'
  | 'rejected'
  | 'expired';

export interface QuoteItem {
  id: number;
  quote_id: number;
  spare_part_id: number | null;
  original_text: string;
  honeywell_code: string;
  description: string;
  quantity: number;
  unit_price: number;
  discount_pct: number;
  line_total: number;
  match_score: number | null;
  match_strategy: string | null;
  is_confirmed: boolean;
  sort_order: number;
  spare_part?: SparePart;
}

export interface Quote {
  id: number;
  quote_number: string;
  customer_id: number;
  email_request_id: number | null;
  created_by: number;
  approved_by: number | null;
  status: QuoteStatus;
  language: string;
  currency: string;
  subtotal: number;
  discount_total: number;
  tax_rate: number;
  tax_amount: number;
  grand_total: number;
  valid_days: number;
  notes: string;
  /**
   * Round-4 R4-TS-2: dropped from `_quote_to_dict` after the audit
   * TS-2 cleanup; consumers should read `has_pdf` instead. Marked
   * optional so the type doesn't lie about always-present.
   */
  pdf_path?: string | null;
  /** Convenience boolean from the serializer (audit TS-2); avoids round-tripping the path. */
  has_pdf?: boolean;
  /** Linked opportunity — needed by the back-link button on quote detail. */
  opportunity_id?: number | null;
  /** Revision tree — points at the prior quote when this is a revision. */
  parent_quote_id?: number | null;
  version: number;
  /** V8 multi-tenant boundary — round-tripped so the UI can verify isolation. */
  tenant_id?: number | null;
  /** Win/loss tracking — populated when status moves to closed_won or closed_lost. */
  closed_at?: string | null;
  close_reason?: string | null;
  created_at: string;
  updated_at: string;
  customer?: Customer;
  items: QuoteItem[];
}

/**
 * Generic in-app notification. Returned by ``notification_service``
 * but the frontend used to ad-hoc this shape per consumer; now
 * centralised so notification UIs (toasts, bell-tray, count badges)
 * agree on the schema.
 */
export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  entity_type?: string | null;
  entity_id?: number | null;
  created_at: string;
}

// ── Dashboard / Analytics ────────────────────────────
export interface DashboardStats {
  total_emails: number;
  parsed_emails: number;
  total_quotes: number;
  sent_quotes: number;
  total_parts: number;
  total_customers: number;
  conversion_rate: number;
  avg_response_hours: number;
  pending_review_count: number;
  pending_value: number;
  // Doughnut chart ratios
  answered_emails: number;
  total_parts_value: number;
  answered_parts_value: number;
  total_parts_count: number;
  answered_parts_count: number;
  approved_quotes: number;
}

export interface TopPart {
  honeywell_code: string;
  name: string;
  name_tr?: string | null;
  name_en?: string | null;
  total_quantity: number;
  request_count: number;
  total_value?: number | null;
}

export interface TrendData {
  year: number;
  month: number;
  quote_count: number;
  revenue: number;
  sent_count: number;
}

// ── Part Matching ────────────────────────────────────
export interface MatchResult {
  part_id: number;
  honeywell_code: string;
  name: string;
  score: number;
  strategy: string;
}

// ── Customer Health ─────────────────────────────────
export interface HealthIndicator {
  name: string;
  label: string;
  score: number;
  weight: number;
  raw_value: string | number;
  description: string;
}

export interface HealthExplanation {
  indicator: string;
  label: string;
  value: string | number | null;
  weight: number;
  contribution: number;
  recommendation: string | null;
}

export interface CustomerHealthReport {
  customer_id: number;
  customer_name: string;
  company: string | null;
  score: number;
  risk_level: 'healthy' | 'at_risk' | 'churning';
  indicators: HealthIndicator[];
  recommendations: string[];
  /** Populated only when the request includes `?include_explanations=true`. */
  explanations?: HealthExplanation[];
}

export interface HealthOverview {
  summary: {
    total_customers: number;
    healthy_count: number;
    at_risk_count: number;
    churning_count: number;
    average_score: number;
  };
  customers: CustomerHealthReport[];
}

export interface AtRiskResponse {
  count: number;
  customers: CustomerHealthReport[];
}

// ── Stage Requirements (Sales Path) ────────────────
export interface StageRequirementStatus {
  stage: string;
  label: string;
  order: number;
  completion_pct: number;
  is_current: boolean;
  required_fields: { name: string; label: string; completed: boolean }[];
  coaching_tips: string[];
}

// ── Pagination ───────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ── Auth ─────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// ── v2: Opportunity ─────────────────────────────────
export interface Opportunity {
  id: number;
  title: string;
  stage: string;
  amount: number | null;
  currency: string;
  close_date: string | null;
  owner_id: number;
  customer_id: number | null;
  status: string;
  probability?: number; // stage probability (0-1 or 0-100, depends on backend)
  // Loss reason (closed-lost detail) and forecast classification
  // (commit / best_case / pipeline / omitted) — both are returned by
  // the backend and now typed so the deal pages can render them.
  loss_reason?: string | null;
  forecast_category?: 'commit' | 'best_case' | 'pipeline' | 'omitted' | null;
  // Segmentation FKs — surfaced for territory + pipeline filters.
  pipeline_id?: number | null;
  territory_id?: number | null;
  // Revenue-leak audit (previous values when stage/close_date/amount
  // last changed). Used by the closed-lost detail page to render
  // the "deal slipped from X → Y" diff.
  previous_stage?: string | null;
  previous_close_date?: string | null;
  previous_amount?: number | null;
  // Round-4 R4-TS-4 — lead-source attribution. Returned by the backend
  // since DB-6 (v1.8.0) but missing from the TS interface so consumers
  // had to cast.
  source?: string | null;
  // Round-4 R4-DTO-1 — round-tripped tenant_id so the UI can verify
  // isolation without re-querying.
  tenant_id?: number | null;
  rotting_days: number;
  last_activity_at?: string | null;
  open_tasks_count?: number;
  customer: { id: number; name: string; company: string } | null;
  owner: { id: number; full_name: string } | null;
  quotes: { id: number; quote_number: string; status: string; grand_total: number }[];
  open_quotes_count?: number;
  created_at: string;
  updated_at: string;
}

// Mirrors backend OpportunitySignalType enum (app/models/enums.py).
// Adding new values here when the backend enum grows keeps switch
// statements / label maps in the UI from silently falling through.
export type OpportunitySignalType =
  | 'pricing_concern'
  | 'competitor'
  | 'objection'
  | 'no_touch'
  | 'discount_risk'
  | 'sla_breach'
  | 'positive'
  | 'workflow_triggered'
  | 'coaching_needed'
  | 'stage_change'
  | 'email_parsed'
  | 'expansion_signal'
  | 'playbook_completed';

export type OpportunitySignalSeverity = 'low' | 'med' | 'high';

export interface OpportunitySignal {
  id: number;
  signal_type: OpportunitySignalType;
  severity: OpportunitySignalSeverity;
  evidence: string | null;
  source_type: string | null;
  source_id: number | null;
  is_resolved: boolean;
  created_at: string | null;
}

export interface TaskItem {
  id: number;
  title: string;
  description: string | null;
  due_at: string | null;
  status: string;
  source: string | null;
  priority: string | null;
  created_at: string | null;
}

export interface OpportunityIntelligenceResponse {
  opportunity: Opportunity;
  health: {
    opportunity_id: number;
    score: number;
    risk_level: string;
    indicators: Array<{
      name: string;
      label: string;
      score: number;
      weight: number;
      raw_value: unknown;
      description: string | null;
    }>;
    recommendations: string[];
  } | null;
  probability: CloseProbabilityResult;
  signals: OpportunitySignal[];
  tasks: TaskItem[];
  open_tasks_count: number;
}

export interface OpportunityEvent {
  id: number;
  event_type: string;
  entity_type: string | null;
  entity_id: number | null;
  description: string | null;
  occurred_at: string | null;
  synthetic?: boolean;
  via_quote?: boolean;
}

export interface OpportunityFeaturesDailyLatest {
  opportunity_id: number;
  snapshot_date: string;
  deal_age_days: number;
  days_since_last_rep_touch: number;
  days_since_last_buyer_touch: number;
  rep_touch_count_14d: number;
  buyer_reply_count_14d: number;
  meeting_count_30d: number;
  quote_count: number;
  latest_discount_pct: number | null;
  competitor_mentions_30d: number;
  pricing_objections_30d: number;
  positive_signal_count_14d: number;
  negative_signal_count_14d: number;
  momentum_score: number | null;
  momentum_band?: string | null;
  momentum_drivers_json?: string | null;
  /** Pre-parsed driver list from the backend (audit TS-4). Avoids
      client-side JSON.parse. Each entry is the deserialized form of
      what's stored in `momentum_drivers_json`. */
  momentum_drivers?: Array<{
    label?: string;
    contribution?: number;
    weight?: number;
    direction?: 'positive' | 'negative' | string;
    [key: string]: unknown;
  }>;
  buyer_state: string | null;
  close_probability: number | null;
  /** V6 trajectory: days the opportunity has spent in its current stage. */
  stage_velocity_days?: number | null;
  /** Optional V6 expansion field; null on rows seeded before V6. */
  objection_density_norm?: number | null;
}

export interface KanbanColumn {
  stage: string;
  count: number;
  total_amount: number;
  items: Opportunity[];
}

export interface BoardSummary {
  window_days: number;
  open_pipeline_total: number;
  won_count: number;
  win_rate: number;
  rotting_count: number;
}

export interface ActivityLogEntry {
  id: number;
  activity_type: string;
  entity_type: string;
  entity_id: number;
  summary: string;
  created_at: string;
}

// ── Approval Routing ──
export interface ApprovalRule {
  id: number;
  name: string;
  entity_type: string;
  condition_type: string;
  threshold_value: number;
  threshold_operator: string;
  approver_role: string | null;
  approver_user_id: number | null;
  priority: number;
  is_active: boolean;
  // Round-4 R4-TS-3 — backend returns these; UI couldn't surface SLA
  // escalation timing without a cast.
  escalation_hours?: number | null;
  escalation_action?: string | null;
  created_at: string | null;
}

export interface ApprovalRequest {
  id: number;
  entity_type: string;
  entity_id: number;
  rule_id: number;
  level: number;
  status: string;
  requested_by: number;
  assigned_to: number;
  decided_by: number | null;
  decided_at: string | null;
  comments: string;
  created_at: string | null;
}

// ── Forecast ──
export interface ForecastAdjustment {
  id: number;
  opportunity_id: number;
  adjusted_by: number;
  original_amount: number;
  adjusted_amount: number;
  original_category: string;
  adjusted_category: string;
  reason: string | null;
  created_at: string | null;
}

export interface PipelineSnapshot {
  id: number;
  snapshot_date: string | null;
  stage: string;
  opportunity_count: number;
  total_amount: number;
  weighted_amount: number;
  created_at: string | null;
}

// ── Deal Health ──
export interface DealHealthIndicator {
  name: string;
  label: string;
  score: number;
  weight: number;
  raw_value: unknown;
  description: string;
}

export interface DealHealthReport {
  opportunity_id: number;
  title: string;
  score: number;
  risk_level: string;
  indicators: DealHealthIndicator[];
  recommendations: string[];
}

export interface DealHealthSummary {
  total_opportunities: number;
  healthy_count: number;
  at_risk_count: number;
  critical_count: number;
  average_score: number;
}

// ── Webhooks ──
export interface WebhookSubscription {
  id: number;
  name: string;
  url: string;
  event_types: string[];
  is_active: boolean;
  created_by: number;
  last_triggered_at: string | null;
  failure_count: number;
  created_at: string | null;
}

export interface WebhookDelivery {
  id: number;
  subscription_id: number;
  event_type: string;
  status_code: number;
  response_body: string;
  delivered_at: string | null;
}

// ── Teams / Sharing ──
export interface TeamMember {
  id: number;
  customer_id: number;
  user_id: number;
  role: string;
  user_email?: string | null;
  user_full_name?: string | null;
}

export interface SharingRule {
  id: number;
  name: string;
  entity_type: string;
  criteria_json: string;
  share_with_role: string | null;
  share_with_user_id: number | null;
  access_level: string;
  is_active: boolean;
}

// ── Reports ──
export interface ReportTemplate {
  id: number;
  name: string;
  description: string | null;
  entity_type: string;
  columns_json: string;
  filters_json: string | null;
  group_by: string | null;
  sort_by: string | null;
  sort_order: string;
  chart_type: string | null;
  is_system: boolean;
  created_by: number | null;
  is_public: boolean;
}

// ── Revenue Cockpit ──────────────────────────────────
export interface RevenueSignalItem {
  id: number;
  signal_type: string;
  source_entity_type: string;
  source_entity_id: number | null;
  opportunity_id: number | null;
  customer_id: number | null;
  owner_id: number | null;
  severity: string;
  confidence: number;
  recommended_action: string | null;
  is_resolved: boolean;
  created_at: string;
}

export interface CockpitKpis {
  pipeline_total: number;
  pipeline_currency: string;
  win_rate: number;
  at_risk_count: number;
  avg_deal_velocity_days: number;
  open_ai_tasks: number;
  signal_stats: {
    total: number;
    by_severity: Record<string, number>;
    by_type: Record<string, number>;
    critical_count: number;
    high_count: number;
  };
}

export interface CockpitAction {
  id: number;
  title: string;
  description: string | null;
  priority: string;
  opportunity_id: number | null;
  owner_id: number | null;
  due_at: string | null;
  created_at: string;
  rotting_days?: number;
  last_activity_at?: string | null;
  open_tasks_count?: number;
  deal_health?: { score: number; risk_level: string } | null;
}

export interface CockpitRiskyAccount {
  customer_id: number;
  customer_name: string;
  company: string | null;
  health_score: number;
  health_risk_level: string;
  active_opportunities: number;
  pipeline_total: number;
  open_tasks_count: number;
  unresolved_high_signals: number;
  last_activity_at: string | null;
}

export interface CockpitMomentumItem {
  id: number;
  title: string;
  stage: string;
  amount: number | null;
  currency: string;
  owner_id: number | null;
  customer_id: number | null;
  momentum_score: number | null;
  momentum_band: string | null;
  drivers: Array<{ label: string; impact: number; value?: unknown }>;
}

export interface CockpitStallingDealItem {
  id: number;
  title: string;
  stage: string;
  amount: number | null;
  currency: string;
  owner_id: number | null;
  customer_id: number | null;
  days_since_last_buyer_touch: number | null;
  buyer_reply_count_14d: number;
  meeting_count_30d: number;
  negative_signal_count_14d: number;
}

export interface CoachingOverview {
  summary: {
    total_reps: number;
    avg_score: number;
    low_performers: number;
  };
  reps: CoachingRepScore[];
}

export interface CoachingRepScore {
  user_id: number;
  user_name: string;
  score: number;
  risk_level: string;
  indicators: {
    name: string;
    label: string;
    score: number;
    weight: number;
  }[];
  recommendations: string[];
}

// ── AI Engine ───────────────────────────────────────
export interface AiTask {
  id: number;
  title: string;
  description: string | null;
  opportunity_id: number | null;
  due_at: string | null;
  status: string;
  source: string;
  priority: string;
  created_at: string;
}

export interface AiSummarySource {
  type: string;
  id: number;
  label: string;
}

export interface AiSummarizeResponse {
  summary: string;
  /** Structured links (preferred) or legacy string labels. */
  sources: (AiSummarySource | string)[];
  cached: boolean;
  generated_at?: string;
  /** Present for `/ai/summarize/changes` responses. */
  days?: number;
}

export interface SavedView {
  id: number;
  name: string;
  route: string;
  query_json: string;
  created_at: string | null;
}

export interface PipelineSuggestion {
  opportunity_id: number;
  current_stage: string;
  suggested_stage: string;
  suggested_next_steps: string[];
  factors: string[];
}

export interface DealRiskResult {
  opportunity_id: number;
  risk_score: number;
  risk_level: string;
  factors: { name: string; score: number; description: string }[];
  recommendations: string[];
}

export interface CompetitiveIntelData {
  competitors: {
    name: string;
    mention_count: number;
    sentiment_avg: number;
    recent_mentions: { source_type: string; context_snippet: string; created_at: string }[];
  }[];
  total_mentions: number;
}

// ── Dashboard Builder ───────────────────────────────
export interface DashboardConfig {
  id: number;
  name: string;
  widgets_json: string;
  is_default: boolean;
  created_at: string | null;
}

export interface DashboardWidget {
  type: string;
  position: { x: number; y: number; w: number; h: number };
  report_id: number | null;
  config: Record<string, unknown>;
}

export interface DashboardExecuteResult {
  id: number;
  name: string;
  widgets: {
    type: string;
    position: { x: number; y: number; w: number; h: number };
    report_id: number | null;
    data: unknown;
    error: string | null;
  }[];
}

// ── Playbook (extended) ─────────────────────────────
export interface Playbook {
  id: number;
  name: string;
  description: string | null;
  trigger_conditions_json: string | null;
  steps_json: string | null;
  category: string | null;
  is_active: boolean;
  created_by: number | null;
  created_at: string;
}

export interface PlaybookExecution {
  id: number;
  playbook_id: number;
  opportunity_id: number | null;
  triggered_by_signal_id?: number | null;
  status: string;
  current_step: number;
  started_at: string;
  completed_at: string | null;
  /** When the next step is scheduled to run (delayed execution). */
  next_action_at?: string | null;
}

export interface PlaybookTemplate {
  id: number;
  name: string;
  description: string | null;
  category: string | null;
  trigger_conditions_json: string | null;
  steps_json: string | null;
}

export interface PlaybookAnalytics {
  total_executions: number;
  total_completed: number;
  // R5-TS-1 / R5-TS-2 — backend returns null when no completions /
  // when total_with or total_without is zero. The previous
  // non-nullable types crashed the analytics page on first load
  // for tenants without playbook history.
  avg_completion_days: number | null;
  win_rate_with_playbook: number | null;
  win_rate_without_playbook: number | null;
  per_playbook: { playbook_id: number; name: string; executions: number; completed: number }[];
  most_triggered: { playbook_id: number; name: string; count: number }[];
}

// ── Coaching (extended) ─────────────────────────────
export interface CoachingPlan {
  id: number;
  user_id: number;
  user_name: string;
  manager_id: number;
  goals_json: string;
  weeks: number;
  start_date: string | null;
  status: string;
  created_at: string;
}

export interface CoachingSnapshot {
  id: number;
  score: number;
  indicators_json: string;
  created_at: string;
}

export interface CoachingBenchmark {
  user_id: number;
  user_name: string;
  score: number;
  rank: number;
  percentile: number;
  snapshot_date: string;
}

// ── Engagement ──────────────────────────────────────
export interface Transcript {
  id: number;
  title: string;
  content: string;
  source: string | null;
  opportunity_id: number | null;
  customer_id: number | null;
  duration_minutes: number | null;
  keywords_found: number;
  summary: string | null;
  action_items_json: string | null;
  sentiment: string | null;
  created_at: string;
}

export interface KeywordPack {
  id: number;
  name: string;
  category: string;
  keywords: string[];
  is_active: boolean;
}

export interface Sequence {
  id: number;
  name: string;
  description: string | null;
  steps: Record<string, unknown>[];
  // Round-4 R4-TS-5 — list endpoint omits this; detail endpoint
  // returns it; downstream parses it as a list. Made optional and
  // accept either shape.
  auto_enroll_rules?: Record<string, unknown> | unknown[] | null;
  created_at: string;
}

export interface SequenceEnrollment {
  id: number;
  sequence_id: number;
  // Round-4 R4-TS-6 — backend returns these on the detail endpoint;
  // UI couldn't surface "next action in N days" without a cast.
  sequence_name?: string | null;
  next_action_at?: string | null;
  opportunity_id: number | null;
  customer_id: number | null;
  lead_id: number | null;
  // Round-4 R4-SHAPE-1 — DB nullable; rendering this as binary gave
  // the wrong status when null.
  is_paused: boolean | null;
  status: string;
  current_step: number;
  exit_reason: string | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface SequenceStepRun {
  id: number;
  step_number: number;
  step_action: string;
  variant_key: string | null;
  status: string;
  reason_codes: string[];
  started_at: string | null;
  completed_at: string | null;
}

// ── Buyer Relationship Map ──────────────────────────
export interface Stakeholder {
  id: number;
  opportunity_id: number | null;
  customer_id: number | null;
  name: string;
  email: string | null;
  title: string | null;
  phone: string | null;
  seniority: string | null;
  department_group: string | null;
  buyer_role: string | null;
  notes: string | null;
  is_auto_detected: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface StakeholderAlert {
  severity: string;
  type: string;
  message: string;
}

// ── Product Bundles (CPQ) ──────────────────────────
export interface ProductBundle {
  id: number;
  name: string;
  description: string | null;
  items: { spare_part_id: number; quantity: number }[];
  bundle_price: number | null;
  discount_pct: number;
  created_at: string | null;
}

export interface Segment {
  id: number;
  name: string;
  description: string | null;
  rules: Record<string, unknown>[];
  customer_count: number;
  created_at: string;
}

export interface EngagementScorecard {
  user_id: number;
  full_name: string;
  total_quotes: number;
  sent_quotes: number;
  emails_assigned: number;
  emails_processed: number;
  process_rate: number;
  signals_detected: number;
  coaching_notes: string | null;
}

// ── Compliance (KVKK) ──────────────────────────────
export interface ConsentStatus {
  customer_id: number;
  has_consent: boolean;
  consent_date: string | null;
  method: string | null;
  purpose: string | null;
  retention_until: string | null;
}

export interface RetentionPolicy {
  id: number;
  entity_type: string;
  retention_days: number;
  action: string;
  is_active: boolean;
  created_at: string | null;
}

export interface BreachNotification {
  id: number;
  breach_type: string;
  description: string | null;
  severity: string;
  status: string;
  notified_at: string | null;
  created_by: number | null;
  created_at: string | null;
}

// ── Integrations ────────────────────────────────────
export interface CalendarStatus {
  connected: boolean;
  provider: string | null;
  status?: string;
  token_present?: boolean;
  last_sync_at?: string | null;
}

export interface EsignStatus {
  connected: boolean;
  provider: string | null;
}

export interface CalendarHealth {
  ok: boolean;
  status: string;
  provider: string | null;
  error?: string;
}

// ── Custom Fields ───────────────────────────────────
export interface CustomFieldDefinition {
  id: number;
  entity_type: string;
  field_name: string;
  field_type: string;
  options_json: string | null;
  is_required: boolean;
  sort_order: number;
  created_at: string | null;
}

export interface CustomFieldValue {
  id: number;
  custom_field_id: number;
  field_name: string;
  field_type: string;
  value_text: string | null;
  value_number: number | null;
  value_date: string | null;
}

// ── Field Permissions ───────────────────────────────
export interface FieldPermission {
  id: number;
  role: string;
  entity_type: string;
  field_name: string;
  access_level: string;
  created_at: string | null;
}

// ── Product Rules ───────────────────────────────────
// ── Playbook Visual Builder ─────────────────────────
export interface TriggerCondition {
  field: string;
  operator: string;
  value: string;
}

export interface PlaybookStepDef {
  action_type: string;
  description?: string;
  template?: string;
  delay_days?: number;
  priority?: string;
  if_true_step?: number;
  if_false_step?: number;
}

// ── Forecast Team Rollup ────────────────────────────
export interface TeamRollupRow {
  user_id: number;
  user_name: string;
  commit: number;
  best_case: number;
  pipeline: number;
  total: number;
  opportunity_count: number;
}

export interface ProductRule {
  id: number;
  spare_part_id: number | null;
  category: string | null;
  rule_type: string;
  condition_json: Record<string, unknown>;
  action_json: Record<string, unknown>;
  priority: number;
  is_active: boolean;
  created_at: string | null;
}

// ── Workflow Rules ─────────────────────────────────
export interface WorkflowRule {
  id: number;
  name: string;
  entity_type: string;
  trigger_event: string;
  conditions_json: string | null;
  actions_json: string;
  flow_json: string | null;
  is_active: boolean;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

// ── AI Predictions ────────────────────────────────────
export interface CloseProbabilityResult {
  close_probability: number; // 0-1 (preferred) or 0-100 (legacy)
  close_probability_pct?: number;
  confidence: string; // legacy alias
  confidence_band?: string;
  factors: {
    name?: string;
    label?: string;
    key?: string;
    impact: string;
    weight?: number;
    evidence: string;
  }[];
  next_steps: string[];
}

export interface ChurnPredictionResult {
  churn_probability: number;
  risk_level: string;
  risk_factors: { name: string; description: string }[];
  retention_actions: string[];
}

// ── Forecast (Hybrid, Sprint 5.4) ───────────────────────
export interface HybridForecastBlock {
  stage: string;
  count: number;
  amount: number;
  legacy_weighted: number;
  hybrid_weighted: number;
}

export interface HybridForecastResponse {
  owner_id: number | null;
  legacy_weighted_total: number;
  hybrid_weighted_total: number;
  by_stage: HybridForecastBlock[];
  by_confidence: Record<string, { count: number; amount: number; hybrid_weighted: number }>;
}

// ── Insights (Signals, Sprint 5) ──────────────────────
export interface SignalsDashboardResponse {
  window_days: number;
  topic_counts: Record<string, number>;
  severity_buckets: Record<string, number>;
  impacted_opportunity_ids: number[];
}

export interface SignalsTrendPoint {
  date: string;
  total: number;
  pricing_concern?: number;
  competitor?: number;
  objection?: number;
  no_touch?: number;
  discount_risk?: number;
}

export interface SignalsTrendResponse {
  window_days: number;
  series: SignalsTrendPoint[];
}

export interface ConversationInsightsResponse {
  window_days: number;
  transcript_keyword_hits: Record<string, number>;
}

export interface ConversationSearchItem {
  type: string;
  id: number;
  title: string;
  snippet: string;
  opportunity_id: number;
  stage: string;
  owner_id: number;
  occurred_at: string | null;
}

export interface ConversationSearchResponse {
  query: string;
  page: number;
  page_size: number;
  total: number;
  items: ConversationSearchItem[];
}

// ── Comment ────────────────────────────────────────
export interface Comment {
  id: number;
  entity_type: string;
  entity_id: number;
  user_id: number;
  body: string;
  mentions_json: string | null;
  parent_id: number | null;
  created_at: string;
  updated_at: string;
  user?: { id: number; full_name: string };
  replies?: Comment[];
}

// ── Activity Capture ───────────────────────────────
export interface ActivityLogFull {
  id: number;
  activity_type: string;
  entity_type: string | null;
  entity_id: number | null;
  opportunity_id: number | null;
  customer_id: number | null;
  user_id: number;
  summary: string;
  duration_minutes: number | null;
  outcome: string | null;
  attendees_json: string | null;
  agenda: string | null;
  created_at: string;
}

export interface ActivityMetrics {
  user_id: number;
  user_name: string;
  calls_per_day: number;
  meetings_per_day: number;
  emails_per_day: number;
  notes_per_day: number;
}

// ── Email Template ────────────────────────────────────
export interface EmailTemplate {
  id: number;
  name: string;
  subject: string;
  body_html: string;
  variables_json: string | null;
  category: string | null;
  is_shared: boolean;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

// ── Stage Config ──────────────────────────────────────
export interface StageConfig {
  id: number;
  stage_name: string;
  label: string;
  probability_pct: number;
  rotting_threshold_days: number;
  sort_order: number;
  is_active: boolean;
}

// ── Activity Summary (Modul 6) ──
export interface ActivitySummary {
  opportunity_id: number;
  total_activities: number;
  by_type: Record<string, number>;
  last_activity_at: string | null;
  days_since_last_activity: number;
  avg_activities_for_stage: number;
}

export interface ActivityDroughtItem {
  id: number;
  title: string;
  stage: string;
  days_since_last: number;
  owner_name: string;
}

// ── Forecast Accuracy (Modul 12) ──
export interface ForecastAccuracyRep {
  user_id: number;
  user_name: string;
  forecast: number;
  actual: number;
  accuracy: number;
}

export interface ForecastAccuracy {
  period: string;
  commit_forecast: number;
  actual_won: number;
  accuracy_pct: number;
  per_rep: ForecastAccuracyRep[];
}

// ── Quote Comparison (Modul 13) ──
export interface QuoteComparisonChange {
  from: number;
  to: number;
}

export interface QuoteComparisonItem {
  key: string;
  description: string;
  quantity: number;
  unit_price: number;
}

export interface QuoteComparisonChangedItem {
  key: string;
  description: string;
  changes: Record<string, QuoteComparisonChange>;
}

export interface QuoteComparisonResult {
  quote_a: number;
  quote_b: number;
  added_items: QuoteComparisonItem[];
  removed_items: QuoteComparisonItem[];
  changed_items: QuoteComparisonChangedItem[];
  summary_diff: {
    subtotal: QuoteComparisonChange;
    grand_total: QuoteComparisonChange;
    currency: { from: string; to: string };
    item_count: QuoteComparisonChange;
  };
}

export interface QuoteVersionItem {
  id: number;
  quote_number: string;
  version: number;
  status: string;
  grand_total: number;
  currency: string;
  parent_quote_id: number | null;
  created_at: string | null;
}

// ── Leaderboard & Gamification ──────────────────────
export interface LeaderboardEntry {
  rank: number;
  user_id: number;
  user_name: string;
  value: number;
  delta_vs_prev_period: number;
}

export interface Achievement {
  id: number;
  achievement_type: string;
  title: string;
  description: string | null;
  earned_at: string | null;
  metadata: Record<string, unknown> | null;
}

// ── Deal Room ──────────────────────────────────────
export interface DealRoom {
  id: number;
  opportunity_id: number;
  name: string;
  external_token: string;
  shared_items_json: string | null;
  mutual_action_plan_json: string | null;
  welcome_message: string | null;
  is_active: boolean;
  last_buyer_activity_at: string | null;
  created_by: number;
  created_at: string | null;
}

// ── Data Quality ────────────────────────────────────
export interface DataQualityDetail {
  field: string;
  weight: number;
  completed: boolean;
}

export interface RevenueWaterfallCategory {
  type: string;
  label: string;
  count: number;
  amount: number;
  positive: boolean;
}

export interface RevenueWaterfallResult {
  from_date: string;
  to_date: string;
  categories: RevenueWaterfallCategory[];
  net_change: number;
  total_events: number;
}

export interface RevenueLeakFactor {
  name: string;
  label: string;
  detail: string;
}

export interface RevenueLeakItem {
  opportunity_id: number;
  title: string;
  stage: string;
  amount: number;
  leak_score: number;
  factors: RevenueLeakFactor[];
  owner_name: string;
}

export interface RevenueLeakResult {
  total_leaks: number;
  total_leak_amount: number;
  items: RevenueLeakItem[];
}

export interface DataQualityOverview {
  // Actual API fields
  customers?: {
    total: number;
    missing_phone: number;
    missing_email: number;
    missing_company: number;
    completeness_pct: number;
  };
  quotes?: {
    total: number;
    missing_customer: number;
    missing_items: number;
    completeness_pct: number;
  };
  // Legacy fields (kept for backward compatibility)
  avg_score?: number;
  avg_customer_score?: number;
  avg_opportunity_score?: number;
  total_customers?: number;
  total_opportunities?: number;
  worst_records?: {
    entity_type: string;
    entity_id: number;
    name: string;
    score: number;
  }[];
  field_completion_rates?: Record<string, number>;
}

// ── Shared Document (Modul 7) ────────────────────────
export interface SharedDocument {
  id: number;
  quote_id: number | null;
  file_name: string;
  file_url: string;
  shared_with_email: string;
  tracking_token: string;
  views_count: number;
  first_viewed_at: string | null;
  last_viewed_at: string | null;
  total_view_seconds: number;
  created_at: string | null;
}

// ── Meeting Scheduler (Modul 11) ────────────────────
export interface MeetingLink {
  id: number;
  slug: string;
  title: string;
  duration_minutes: number;
  is_active: boolean;
  booking_url?: string;
  created_at: string | null;
}

export interface MeetingBooking {
  id: number;
  meeting_link_id: number;
  booker_name: string;
  booker_email: string;
  scheduled_at: string;
  notes: string | null;
  status: string;
  created_at: string | null;
}

// ── Subscription & Recurring Revenue ────────────────
export interface Subscription {
  id: number;
  customer_id: number;
  quote_id: number | null;
  name: string;
  status: string;
  billing_cycle: string;
  start_date: string;
  end_date: string | null;
  mrr: number;
  next_renewal_date: string | null;
  auto_renew: boolean;
  items_json: string | null;
  currency: string;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface MrrDashboard {
  total_mrr: number;
  active_count: number;
  churn_count: number;
  churned_mrr: number;
  upcoming_renewals: {
    id: number;
    name: string;
    customer_id: number;
    next_renewal_date: string | null;
    mrr: number;
  }[];
  top_customers: {
    customer_id: number;
    name: string;
    mrr: number;
  }[];
}

// ── Guided Selling (CPQ Wizard) ─────────────────────
export interface SellingGuideStep {
  question: string;
  options: string[];
  field: string;
}

export interface SellingGuideRule {
  conditions: Record<string, string>;
  suggest_parts: number[];
  suggest_bundles: number[];
}

export interface SellingGuide {
  id: number;
  name: string;
  description: string | null;
  steps: SellingGuideStep[];
  product_rules: SellingGuideRule[];
  is_active: boolean;
  created_by: number | null;
  created_at: string | null;
}

export interface GuidedSellingSuggestion {
  suggested_parts: {
    id: number;
    honeywell_code: string;
    name: string;
    unit_price: number;
  }[];
  suggested_bundles: {
    id: number;
    name: string;
    description: string | null;
    bundle_price: number | null;
  }[];
  match_count: number;
}

// ── Campaigns ──
export interface Campaign {
  id: number;
  name: string;
  type: string;
  status: string;
  description?: string;
  start_date?: string;
  end_date?: string;
  budget?: number;
  actual_cost: number;
  expected_revenue?: number;
  actual_revenue: number;
  created_by: number;
  created_at: string;
  updated_at: string;
  member_count?: number;
}

export interface CampaignMember {
  id: number;
  campaign_id: number;
  lead_id?: number;
  customer_id?: number;
  status: string;
  responded_at?: string;
  created_at: string;
  lead?: { id: number; first_name: string; last_name: string; email: string };
  customer?: { id: number; name: string; email: string; company: string };
}

export interface CampaignROI {
  actual_revenue: number;
  actual_cost: number;
  roi_pct: number;
  member_count: number;
  responded_count: number;
  conversion_rate: number;
}

// ── Contract Lifecycle ──────────────────────────────
// ── Invoices ──
export interface Invoice {
  id: number;
  invoice_number: string;
  quote_id?: number;
  contract_id?: number;
  customer_id: number;
  created_by: number;
  issue_date?: string;
  due_date?: string;
  status: string;
  currency: string;
  subtotal: number;
  tax_rate: number;
  tax_amount: number;
  grand_total: number;
  items_json?: string;
  notes?: string;
  pdf_path?: string;
  paid_at?: string;
  created_at: string;
  updated_at: string;
  customer?: { id: number; name: string; company: string };
}

export interface SignatureRequest {
  id: number;
  document_type: string;
  document_id: number;
  signer_email: string;
  signer_name?: string;
  status: string;
  token: string;
  signed_at?: string;
  viewed_at?: string;
  expires_at: string;
  created_at: string;
}

export interface ContractAmendment {
  id: number;
  amendment_type: string;
  changes_json: string | null;
  effective_date: string | null;
  approved_by: number | null;
  created_at: string | null;
}

export interface Contract {
  id: number;
  customer_id: number;
  quote_id: number | null;
  title: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  value: number | null;
  terms_json: string | null;
  signed_at: string | null;
  signed_by: string | null;
  created_by: number;
  created_at: string | null;
  updated_at: string | null;
  amendments: ContractAmendment[];
}

// ── Pipelines ──
export interface Pipeline {
  id: number;
  name: string;
  stages_json?: string;
  is_default: boolean;
  description?: string;
  created_by: number;
  created_at: string;
  // Round-4 R4-TS-7 — backend returns updated_at; TS used to drop it.
  updated_at?: string | null;
}

// ── Territories ──
export interface Territory {
  id: number;
  name: string;
  parent_id?: number;
  description?: string;
  region?: string;
  rules_json?: string;
  created_by: number;
  created_at: string;
  // Round-4 R4-TS-8 — backend returns updated_at; TS used to drop it.
  updated_at?: string | null;
  children?: Territory[];
}

export interface TerritoryAssignment {
  id: number;
  territory_id: number;
  user_id: number;
  role: string;
  created_at: string;
  user?: { id: number; full_name: string; email: string };
}

// ── Lead ─────────────────────────────────────────────
// Round-4 R4-TS-10 — promoted from feature-local interface in
// LeadListPage.tsx. The local copy was missing notes / owner_id /
// owner_name / updated_at / tenant_id, so consumers either dropped
// those fields or had to cast.
export interface Lead {
  id: number;
  // Round-4 R4-DTO-2 — round-tripped tenant_id.
  tenant_id?: number | null;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string | null;
  company: string | null;
  title: string | null;
  source: string;
  status: string;
  lead_score: number;
  owner_id: number | null;
  owner_name: string | null;
  notes: string | null;
  converted_customer_id: number | null;
  converted_opportunity_id: number | null;
  converted_at: string | null;
  created_at: string;
  updated_at: string | null;
  // Detail-only — populated by the rescore endpoint.
  score_breakdown?: Array<{ name: string; label: string; points: number }>;
}

// ── Pricing ──────────────────────────────────────────
export interface PriceTier {
  id: number;
  price_entry_id: number;
  min_qty: number;
  max_qty?: number;
  unit_price: number;
  discount_pct: number;
}

export interface CustomerPricing {
  id: number;
  customer_id: number;
  spare_part_id: number;
  contracted_price: number;
  currency: string;
  discount_pct: number;
  valid_from?: string;
  valid_until?: string;
  notes?: string;
  spare_part?: { id: number; part_number: string; description: string };
}

// ── Revenue Recognition ──────────────────────────────
export interface RevenueSchedule {
  id: number;
  contract_id: number;
  recognition_type: string;
  start_date: string;
  end_date: string;
  total_amount: number;
  recognized_amount: number;
  currency: string;
  created_at: string;
  contract?: { id: number; title: string };
  entries?: RevenueScheduleEntry[];
}

export interface RevenueScheduleEntry {
  id: number;
  schedule_id: number;
  period: string;
  amount: number;
  recognized_amount: number;
  status: string;
  recognized_at?: string;
}

// ── Chat ─────────────────────────────────────────────
export interface ChatSession {
  id: number;
  visitor_id: string;
  assigned_agent_id?: number;
  status: string;
  metadata_json?: string;
  created_at: string;
  agent?: { id: number; full_name: string };
  unread_count?: number;
}

export interface ChatMessage {
  id: number;
  session_id: number;
  sender_type: string;
  sender_id?: string;
  content: string;
  message_type: string;
  is_read: boolean;
  created_at: string;
}

// Re-export so consumers can import from the canonical types module
// (the interface is defined in api.ts to keep it next to the v5 client).
export type { IntelligenceDriver } from './api';
