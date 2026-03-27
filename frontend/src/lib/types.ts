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
  created_at: string;
}

// ── Spare Part ───────────────────────────────────────
export interface SparePart {
  id: number;
  honeywell_code: string;
  name_en: string;
  name_tr: string;
  description_en: string;
  description_tr: string;
  category: string;
  subcategory: string;
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
  total_quantity: number;
  request_count: number;
}

export interface TrendData {
  period: string;
  quote_count: number;
  total_value: number;
}

// ── Part Matching ────────────────────────────────────
export interface MatchResult {
  part_id: number;
  honeywell_code: string;
  name: string;
  score: number;
  strategy: string;
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
