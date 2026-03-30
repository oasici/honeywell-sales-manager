/**
 * Format a number as currency (Turkish locale).
 * Defaults to USD if no currency specified.
 */
export function formatCurrency(amount: number | null | undefined, currency: string = 'USD'): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount ?? 0);
}

/** Format an ISO date string as Turkish date (dd.MM.yyyy) */
export function formatDate(date: string): string {
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(date));
}

/** Format an ISO date string as Turkish date-time (dd.MM.yyyy HH:mm) */
export function formatDateTime(date: string): string {
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date));
}

/** Format a decimal as percentage string */
export function formatPercent(value: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

/** Format a number with Turkish locale grouping */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('tr-TR').format(value);
}
