/**
 * Format helpers (locale-aware).
 */
import { usePreferencesStore } from '../stores/preferencesStore';

type Language = 'tr' | 'en' | 'de' | 'fr' | 'es';

export function languageToLocale(language: string | null | undefined): string {
  const lang = (language || 'tr') as Language;
  switch (lang) {
    case 'en':
      return 'en-US';
    case 'de':
      return 'de-DE';
    case 'fr':
      return 'fr-FR';
    case 'es':
      return 'es-ES';
    case 'tr':
    default:
      return 'tr-TR';
  }
}

/** Active UI locale (from preferences store). Safe outside React. */
export function currentLocale(): string {
  try {
    return languageToLocale(usePreferencesStore.getState().language);
  } catch {
    return 'tr-TR';
  }
}

/**
 * Coerce a value that may be number, string, null, or undefined into a
 * number. Round-10 R10-FE-14 — backend currency columns were
 * migrated from Float to NUMERIC(19, 2). With `asdecimal=False` the
 * wire format stays as a JSON number, but the boundary is now one
 * accidental dependency change away from serialising Decimal as a
 * string. Every numeric helper accepts both shapes so a future
 * Pydantic `from_attributes` tweak that flips Decimal → string does
 * not break the UI.
 */
function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function formatCurrency(
  amount: number | string | null | undefined,
  currency: string = 'USD',
  locale: string = currentLocale(),
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(toNumber(amount));
}

// R5-TS-9..16 — many ``created_at`` / ``received_at`` fields became
// nullable to match the backend's defensive ``isoformat() if x else
// None``. formatDate / formatDateTime now accept null and return an
// em-dash so consumers don't have to wrap every callsite in a guard.
export function formatDate(
  date: string | null | undefined,
  locale: string = currentLocale(),
): string {
  if (!date) return '—';
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(date));
}

export function formatDateTime(
  date: string | null | undefined,
  locale: string = currentLocale(),
): string {
  if (!date) return '—';
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date));
}

/** Format a decimal as percentage string */
export function formatPercent(
  value: number | string | null | undefined,
  locale: string = currentLocale(),
): string {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(toNumber(value) / 100);
}

export function formatNumber(
  value: number | string | null | undefined,
  locale: string = currentLocale(),
): string {
  return new Intl.NumberFormat(locale).format(toNumber(value));
}

export function getCollator(locale: string = currentLocale()): Intl.Collator {
  return new Intl.Collator(locale, { sensitivity: 'base', numeric: true });
}

// Backward compatible export (historical usage)
export const TR_COLLATOR = getCollator('tr-TR');

/** Turkish-safe lowercase (İ→i, I→ı) */
export function toLowerTR(str: string): string {
  return str.toLocaleLowerCase('tr');
}

/** Turkish-safe uppercase (i→İ, ı→I) */
export function toUpperTR(str: string): string {
  return str.toLocaleUpperCase('tr');
}

/**
 * Locale-aware relative time. Uses Intl.RelativeTimeFormat so the
 * units (second / minute / hour / day) and pluralisation match the
 * user's selected language. Round-10 R10-FE-8 — previously every
 * caller wrote its own Turkish-only `formatRelativeTime` that
 * leaked "az önce" / "d once" into every locale.
 */
export function formatRelativeTime(
  iso: string | null | undefined,
  locale: string = currentLocale(),
): string {
  if (!iso) return '—';
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return '—';
  const seconds = Math.round(ms / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (seconds < 60) return rtf.format(-seconds, 'second');
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return rtf.format(-minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (hours < 24) return rtf.format(-hours, 'hour');
  const days = Math.round(hours / 24);
  if (days < 7) return rtf.format(-days, 'day');
  const weeks = Math.round(days / 7);
  if (weeks < 5) return rtf.format(-weeks, 'week');
  const months = Math.round(days / 30);
  if (months < 12) return rtf.format(-months, 'month');
  const years = Math.round(days / 365);
  return rtf.format(-years, 'year');
}
