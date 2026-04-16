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
  name: string;
  company: string;
  email: string;
  phone: string;
  address: string;
  tax_id: string;
  preferred_lang: string;
  created_at: string;
  quote_count?: number;
  total_quote_value?: number;
  industry?: string | null;
  employee_count?: number | null;
  annual_revenue?: string | null;
  website?: string | null;
  linkedin_url?: string | null;
  enriched_at?: string | null;
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
  price_sensitivity: string | null;
  review_status: string | null;
  assigned_to: number | null;
  reviewed_by: number | null;
  is_read: boolean;
  last_parsed_at: string | null;
  created_at: string;
}

// ── Spare Part ───────────────────────────────────────
export interface SparePart {
  id: number;
  honeywell_code: string;
  model_number?: string | null;
  info?: string | null;
  name_en: string;
  name_tr: string;
  description_en: string;
  description_tr: string;
  category: string;
  subcategory: string;
  transfer_price?: number | null;
  supplier_price?: number | null;
  price_currency?: string | null;
  is_active: boolean;
  has_price: boolean;
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
  status: string;
  language: string;
  currency: string;
  subtotal: number;
  discount_total: number;
  tax_rate: number;
  tax_amount: number;
  grand_total: number;
  valid_days: number;
  notes: string;
  pdf_path: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  customer?: Customer;
  items: QuoteItem[];
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

export interface CustomerHealthReport {
  customer_id: number;
  customer_name: string;
  company: string | null;
  score: number;
  risk_level: 'healthy' | 'at_risk' | 'churning';
  indicators: HealthIndicator[];
  recommendations: string[];
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
  rotting_days: number;
  customer: { id: number; name: string; company: string } | null;
  owner: { id: number; full_name: string } | null;
  quotes: { id: number; quote_number: string; status: string; grand_total: number }[];
  open_quotes_count?: number;
  created_at: string;
  updated_at: string;
}

export interface OpportunityEvent {
  id: number;
  event_type: string;
  entity_type: string | null;
  entity_id: number | null;
  description: string | null;
  occurred_at: string;
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

export interface AiSummarizeResponse {
  summary: string;
  sources: string[];
  cached: boolean;
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
  status: string;
  current_step: number;
  started_at: string;
  completed_at: string | null;
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
  avg_completion_days: number;
  win_rate_with_playbook: number;
  win_rate_without_playbook: number;
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
  auto_enroll_rules: Record<string, unknown> | null;
  created_at: string;
}

export interface SequenceEnrollment {
  id: number;
  sequence_id: number;
  opportunity_id: number | null;
  customer_id: number | null;
  lead_id: number | null;
  is_paused: boolean;
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
}

export interface EsignStatus {
  connected: boolean;
  provider: string | null;
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
  close_probability: number;
  confidence: string;
  factors: { name: string; impact: string; evidence: string }[];
  next_steps: string[];
}

export interface ChurnPredictionResult {
  churn_probability: number;
  risk_level: string;
  risk_factors: { name: string; description: string }[];
  retention_actions: string[];
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
