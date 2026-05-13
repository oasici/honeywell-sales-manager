import { AlertCircle } from 'lucide-react';
import { Button } from './Button';
import { useT } from '../../hooks/useT';

/**
 * Round-13 R13-FE-1 — shared "the query failed, retry it" surface.
 *
 * Detail pages (CustomerDetailPage, OpportunityDetailPage, etc.) stack
 * 20+ useQuery hooks, and the previous pattern of "silently render
 * nothing when isError" hid backend outages from operators. This
 * primitive gives every panel a consistent recovery affordance:
 *   - inline (default): a compact red-tinted strip that fits inside a Card
 *   - block: a tall variant for full-section failures
 *
 * Title falls back to the localised "veri yüklenemedi" string; pass
 * a custom title when the panel context warrants it (e.g. "Activities
 * could not be loaded"). The retry handler is required — the whole
 * point of this primitive is to give the user a button to press.
 */
interface QueryErrorBannerProps {
  title?: string;
  description?: string;
  onRetry: () => void;
  variant?: 'inline' | 'block';
  /** Optional secondary action (e.g. "Open support ticket"). */
  secondaryAction?: { label: string; onClick: () => void };
}

export function QueryErrorBanner({
  title,
  description,
  onRetry,
  variant = 'inline',
  secondaryAction,
}: QueryErrorBannerProps) {
  const t = useT();
  const resolvedTitle = title ?? t('common.error_load_failed');

  if (variant === 'block') {
    return (
      <div
        role="alert"
        className="flex flex-col items-center justify-center gap-3 rounded-[16px] border border-red-200 bg-red-50/40 px-6 py-10 text-center dark:border-red-900/40 dark:bg-red-950/20"
      >
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-[12px] bg-red-50 text-red-500 ring-1 ring-inset ring-red-100 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-900/50">
          <AlertCircle size={20} />
        </span>
        <div>
          <p className="text-heading-4 text-slate-900 dark:text-slate-100">{resolvedTitle}</p>
          {description && (
            <p className="mt-1 max-w-[360px] text-body text-slate-500 dark:text-slate-400">
              {description}
            </p>
          )}
        </div>
        <div className="mt-1 flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={onRetry}>
            {t('common.retry')}
          </Button>
          {secondaryAction && (
            <Button size="sm" variant="ghost" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-[12px] border border-red-200 bg-red-50/60 px-3 py-2.5 text-[13px] dark:border-red-900/40 dark:bg-red-950/20"
    >
      <AlertCircle
        size={16}
        className="mt-0.5 shrink-0 text-red-500 dark:text-red-400"
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-red-900 dark:text-red-200">{resolvedTitle}</p>
        {description && (
          <p className="mt-0.5 text-[12px] text-red-800/80 dark:text-red-300/80">{description}</p>
        )}
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="shrink-0 rounded-[8px] px-2 py-1 text-[12px] font-semibold text-red-700 transition-colors hover:bg-red-100 focus:outline-none focus:ring-[3px] focus:ring-red-200 dark:text-red-300 dark:hover:bg-red-900/30 dark:focus:ring-red-900/40"
      >
        {t('common.retry')}
      </button>
    </div>
  );
}
