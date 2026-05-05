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

export function formatCurrency(
  amount: number | null | undefined,
  currency: string = 'USD',
  locale: string = currentLocale(),
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount ?? 0);
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
export function formatPercent(value: number, locale: string = currentLocale()): string {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

export function formatNumber(value: number, locale: string = currentLocale()): string {
  return new Intl.NumberFormat(locale).format(value);
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
