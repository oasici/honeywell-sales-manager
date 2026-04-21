import type { TranslationKey } from './i18n';

export type TranslateFn = (key: TranslationKey) => string;

/** Maps API user roles to existing admin.* i18n keys */
export const USER_ROLE_LABEL_KEYS = {
  admin: 'admin.role_admin',
  sales_manager: 'admin.role_sales_manager',
  sales_rep: 'admin.role_sales_rep',
  viewer: 'admin.role_viewer',
} as const satisfies Record<string, TranslationKey>;

export function translateUserRole(role: string, t: TranslateFn): string {
  const key = USER_ROLE_LABEL_KEYS[role as keyof typeof USER_ROLE_LABEL_KEYS];
  return key ? t(key) : role;
}

export const STATUS_LABEL_KEYS = {
  received: 'labels.status.received',
  parsing: 'labels.status.parsing',
  parsed: 'labels.status.parsed',
  parse_failed: 'labels.status.parse_failed',
  processed: 'labels.status.processed',
  ignored: 'labels.status.ignored',
  draft: 'labels.status.draft',
  pending_approval: 'labels.status.pending_approval',
  approved: 'labels.status.approved',
  sent: 'labels.status.sent',
  accepted: 'labels.status.accepted',
  rejected: 'labels.status.rejected',
  expired: 'labels.status.expired',
  cancelled: 'labels.status.cancelled',
} as const satisfies Record<string, TranslationKey>;

export function translateStatus(status: string, t: TranslateFn): string {
  const key = STATUS_LABEL_KEYS[status as keyof typeof STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

/** Stable order for email category filters (matches former constants.ts) */
export const EMAIL_CATEGORY_VALUES = [
  'spare_part_request',
  'price_inquiry',
  'order_followup',
  'complaint',
  'general_inquiry',
  'other',
] as const;

export const EMAIL_CATEGORY_LABEL_KEYS = {
  spare_part_request: 'labels.email_category.spare_part_request',
  price_inquiry: 'labels.email_category.price_inquiry',
  order_followup: 'labels.email_category.order_followup',
  complaint: 'labels.email_category.complaint',
  general_inquiry: 'labels.email_category.general_inquiry',
  other: 'labels.email_category.other',
} as const satisfies Record<(typeof EMAIL_CATEGORY_VALUES)[number], TranslationKey>;

export function translateEmailCategory(category: string, t: TranslateFn): string {
  const key = EMAIL_CATEGORY_LABEL_KEYS[category as keyof typeof EMAIL_CATEGORY_LABEL_KEYS];
  return key ? t(key) : category;
}

export const REVIEW_STATUS_LABEL_KEYS = {
  pending_review: 'labels.review_status.pending_review',
  pending: 'labels.review_status.pending',
  approved: 'labels.review_status.approved',
  rejected: 'labels.review_status.rejected',
  needs_edit: 'labels.review_status.needs_edit',
} as const satisfies Record<string, TranslationKey>;

export function translateReviewStatus(status: string, t: TranslateFn): string {
  const key = REVIEW_STATUS_LABEL_KEYS[status as keyof typeof REVIEW_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

/** Lead pipeline — maps to existing leads.status_* keys */
export const LEAD_STATUS_LABEL_KEYS = {
  new: 'leads.status_new',
  contacted: 'leads.status_contacted',
  qualified: 'leads.status_qualified',
  unqualified: 'leads.status_unqualified',
  converted: 'leads.status_converted',
} as const satisfies Record<string, TranslationKey>;

export const LEAD_STATUS_VALUES = [
  'new',
  'contacted',
  'qualified',
  'unqualified',
  'converted',
] as const;

export function translateLeadStatus(status: string, t: TranslateFn): string {
  const key = LEAD_STATUS_LABEL_KEYS[status as keyof typeof LEAD_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

/** Invoice — maps to invoices.status_* keys */
export const INVOICE_STATUS_LABEL_KEYS = {
  draft: 'invoices.status_draft',
  sent: 'invoices.status_sent',
  paid: 'invoices.status_paid',
  overdue: 'invoices.status_overdue',
  voided: 'invoices.status_voided',
} as const satisfies Record<string, TranslationKey>;

export const INVOICE_STATUS_VALUES = ['draft', 'sent', 'paid', 'overdue', 'voided'] as const;

export function translateInvoiceStatus(status: string, t: TranslateFn): string {
  const key = INVOICE_STATUS_LABEL_KEYS[status as keyof typeof INVOICE_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const CAMPAIGN_STATUS_LABEL_KEYS = {
  draft: 'labels.campaign_status.draft',
  active: 'labels.campaign_status.active',
  paused: 'labels.campaign_status.paused',
  completed: 'labels.campaign_status.completed',
} as const satisfies Record<string, TranslationKey>;

export const CAMPAIGN_STATUS_VALUES = ['draft', 'active', 'paused', 'completed'] as const;

export function translateCampaignStatus(status: string, t: TranslateFn): string {
  const key = CAMPAIGN_STATUS_LABEL_KEYS[status as keyof typeof CAMPAIGN_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const CAMPAIGN_TYPE_LABEL_KEYS = {
  email: 'campaigns.type.email',
  event: 'campaigns.type.event',
  webinar: 'campaigns.type.webinar',
  social: 'campaigns.type.social',
  content: 'campaigns.type.content',
  other: 'campaigns.type.other',
} as const satisfies Record<string, TranslationKey>;

export function translateCampaignType(type: string, t: TranslateFn): string {
  const key = CAMPAIGN_TYPE_LABEL_KEYS[type as keyof typeof CAMPAIGN_TYPE_LABEL_KEYS];
  return key ? t(key) : type;
}

export const CAMPAIGN_MEMBER_STATUS_LABEL_KEYS = {
  sent: 'campaigns.member_status.sent',
  opened: 'campaigns.member_status.opened',
  clicked: 'campaigns.member_status.clicked',
  responded: 'campaigns.member_status.responded',
  converted: 'campaigns.member_status.converted',
  unsubscribed: 'campaigns.member_status.unsubscribed',
} as const satisfies Record<string, TranslationKey>;

export const CAMPAIGN_MEMBER_STATUS_VALUES = [
  'sent',
  'opened',
  'clicked',
  'responded',
  'converted',
  'unsubscribed',
] as const;

export function translateCampaignMemberStatus(status: string, t: TranslateFn): string {
  const key =
    CAMPAIGN_MEMBER_STATUS_LABEL_KEYS[status as keyof typeof CAMPAIGN_MEMBER_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const CONTRACT_STATUS_LABEL_KEYS = {
  draft: 'labels.contract_status.draft',
  active: 'labels.contract_status.active',
  amended: 'labels.contract_status.amended',
  expired: 'labels.contract_status.expired',
  terminated: 'labels.contract_status.terminated',
} as const satisfies Record<string, TranslationKey>;

export const CONTRACT_STATUS_VALUES = [
  'draft',
  'active',
  'amended',
  'expired',
  'terminated',
] as const;

export function translateContractStatus(status: string, t: TranslateFn): string {
  const key = CONTRACT_STATUS_LABEL_KEYS[status as keyof typeof CONTRACT_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const CONTRACT_AMENDMENT_LABEL_KEYS = {
  extension: 'labels.contract_amendment.extension',
  modification: 'labels.contract_amendment.modification',
  termination: 'labels.contract_amendment.termination',
} as const satisfies Record<string, TranslationKey>;

export const CONTRACT_AMENDMENT_VALUES = ['extension', 'modification', 'termination'] as const;

export function translateContractAmendmentType(type: string, t: TranslateFn): string {
  const key = CONTRACT_AMENDMENT_LABEL_KEYS[type as keyof typeof CONTRACT_AMENDMENT_LABEL_KEYS];
  return key ? t(key) : type;
}

export const CHAT_SESSION_STATUS_LABEL_KEYS = {
  open: 'labels.chat_session.open',
  assigned: 'labels.chat_session.assigned',
  closed: 'labels.chat_session.closed',
} as const satisfies Record<string, TranslationKey>;

export const CHAT_SESSION_STATUS_VALUES = ['open', 'assigned', 'closed'] as const;

export function translateChatSessionStatus(status: string, t: TranslateFn): string {
  const key = CHAT_SESSION_STATUS_LABEL_KEYS[status as keyof typeof CHAT_SESSION_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const COACHING_RISK_LABEL_KEYS = {
  healthy: 'labels.coaching_risk.healthy',
  needs_improvement: 'labels.coaching_risk.needs_improvement',
  at_risk: 'labels.coaching_risk.at_risk',
} as const satisfies Record<string, TranslationKey>;

export const COACHING_RISK_VALUES = ['healthy', 'needs_improvement', 'at_risk'] as const;

export function translateCoachingRisk(risk: string, t: TranslateFn): string {
  const key = COACHING_RISK_LABEL_KEYS[risk as keyof typeof COACHING_RISK_LABEL_KEYS];
  return key ? t(key) : risk;
}

export const COACHING_PLAN_STATUS_LABEL_KEYS = {
  active: 'labels.coaching_plan_status.active',
  completed: 'labels.coaching_plan_status.completed',
  cancelled: 'labels.coaching_plan_status.cancelled',
  draft: 'labels.coaching_plan_status.draft',
} as const satisfies Record<string, TranslationKey>;

export const COACHING_PLAN_STATUS_VALUES = ['active', 'completed', 'cancelled', 'draft'] as const;

export function translateCoachingPlanStatus(status: string, t: TranslateFn): string {
  const key =
    COACHING_PLAN_STATUS_LABEL_KEYS[status as keyof typeof COACHING_PLAN_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const REVENUE_ENTRY_STATUS_LABEL_KEYS = {
  pending: 'labels.revenue_entry_status.pending',
  recognized: 'labels.revenue_entry_status.recognized',
  adjusted: 'labels.revenue_entry_status.adjusted',
} as const satisfies Record<string, TranslationKey>;

export const REVENUE_ENTRY_STATUS_VALUES = ['pending', 'recognized', 'adjusted'] as const;

export function translateRevenueEntryStatus(status: string, t: TranslateFn): string {
  const key =
    REVENUE_ENTRY_STATUS_LABEL_KEYS[status as keyof typeof REVENUE_ENTRY_STATUS_LABEL_KEYS];
  return key ? t(key) : status;
}

export const REVENUE_RECOGNITION_TYPE_LABEL_KEYS = {
  straight_line: 'labels.revenue_recognition_type.straight_line',
  milestone: 'labels.revenue_recognition_type.milestone',
  percentage_completion: 'labels.revenue_recognition_type.percentage_completion',
  point_in_time: 'labels.revenue_recognition_type.point_in_time',
} as const satisfies Record<string, TranslationKey>;

export const REVENUE_RECOGNITION_TYPE_VALUES = [
  'straight_line',
  'milestone',
  'percentage_completion',
  'point_in_time',
] as const;

export function translateRevenueRecognitionType(type: string, t: TranslateFn): string {
  const key =
    REVENUE_RECOGNITION_TYPE_LABEL_KEYS[type as keyof typeof REVENUE_RECOGNITION_TYPE_LABEL_KEYS];
  return key ? t(key) : type;
}

export const PLAYBOOK_CATEGORY_LABEL_KEYS = {
  retention: 'labels.playbook_category.retention',
  growth: 'labels.playbook_category.growth',
  pipeline: 'labels.playbook_category.pipeline',
} as const satisfies Record<string, TranslationKey>;

export const PLAYBOOK_CATEGORY_VALUES = ['retention', 'growth', 'pipeline'] as const;

export function translatePlaybookCategory(category: string, t: TranslateFn): string {
  const key = PLAYBOOK_CATEGORY_LABEL_KEYS[category as keyof typeof PLAYBOOK_CATEGORY_LABEL_KEYS];
  return key ? t(key) : category;
}
