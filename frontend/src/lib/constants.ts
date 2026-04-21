// Tailwind badge classes for email & quote statuses (language-agnostic).
// Human-readable labels: use translateStatus / translateReviewStatus / translateEmailCategory
// from `labelTranslations.ts` with `useT()`.

export const STATUS_COLORS: Record<string, string> = {
  received: 'bg-blue-100 text-blue-800',
  parsing: 'bg-yellow-100 text-yellow-800',
  parsed: 'bg-green-100 text-green-800',
  parse_failed: 'bg-red-100 text-red-800',
  processed: 'bg-emerald-100 text-emerald-800',
  ignored: 'bg-gray-100 text-gray-800',
  draft: 'bg-gray-100 text-gray-800',
  pending_approval: 'bg-amber-100 text-amber-800',
  approved: 'bg-green-100 text-green-800',
  sent: 'bg-blue-100 text-blue-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  expired: 'bg-orange-100 text-orange-800',
  cancelled: 'bg-gray-100 text-gray-500',
};

export const REVIEW_STATUS_COLORS: Record<string, string> = {
  pending_review: 'bg-yellow-100 text-yellow-800',
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  needs_edit: 'bg-orange-100 text-orange-800',
};
