// ── Email & Quote Status Labels (Turkish) ────────────
export const STATUS_LABELS: Record<string, string> = {
  // Email statuses
  received: 'Alındı',
  parsing: 'Ayrıştırılıyor',
  parsed: 'Ayrıştırıldı',
  parse_failed: 'Ayrıştırma Hatası',
  processed: 'İşlendi',
  ignored: 'Yok Sayıldı',
  // Quote statuses
  draft: 'Taslak',
  pending_approval: 'Onay Bekliyor',
  approved: 'Onaylandı',
  sent: 'Gönderildi',
  accepted: 'Kabul Edildi',
  rejected: 'Reddedildi',
  expired: 'Süresi Doldu',
  cancelled: 'İptal Edildi',
};

export const STATUS_COLORS: Record<string, string> = {
  // Email statuses
  received: 'bg-blue-100 text-blue-800',
  parsing: 'bg-yellow-100 text-yellow-800',
  parsed: 'bg-green-100 text-green-800',
  parse_failed: 'bg-red-100 text-red-800',
  processed: 'bg-emerald-100 text-emerald-800',
  ignored: 'bg-gray-100 text-gray-800',
  // Quote statuses
  draft: 'bg-gray-100 text-gray-800',
  pending_approval: 'bg-amber-100 text-amber-800',
  approved: 'bg-green-100 text-green-800',
  sent: 'bg-blue-100 text-blue-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  expired: 'bg-orange-100 text-orange-800',
  cancelled: 'bg-gray-100 text-gray-500',
};

// ── Roles ────────────────────────────────────────────
export const ROLE_LABELS: Record<string, string> = {
  admin: 'Yönetici',
  sales_rep: 'Satış Temsilcisi',
  sales_manager: 'Satış Müdürü',
  operations: 'Operasyon',
  viewer: 'Görüntüleyici',
};

// ── Email Categories ─────────────────────────────────
export const CATEGORY_LABELS: Record<string, string> = {
  spare_part_request: 'Yedek Parça Talebi',
  price_inquiry: 'Fiyat Sorgusu',
  order_followup: 'Sipariş Takibi',
  complaint: 'Şikayet',
  general_inquiry: 'Genel Bilgi',
  other: 'Diğer',
};

// ── Review Status ────────────────────────────────────
export const REVIEW_STATUS_LABELS: Record<string, string> = {
  pending_review: 'Inceleme Bekleniyor',
  pending: 'Inceleme Bekleniyor',
  approved: 'Onaylandi',
  rejected: 'Reddedildi',
  needs_edit: 'Duzenleme Gerekli',
};

export const REVIEW_STATUS_COLORS: Record<string, string> = {
  pending_review: 'bg-yellow-100 text-yellow-800',
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  needs_edit: 'bg-orange-100 text-orange-800',
};
