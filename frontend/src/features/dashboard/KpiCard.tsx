import React from 'react';

/**
 * KpiCard — single-value tile used by the dashboard KPI strip.
 *
 * Visual:
 *   - text-overline label (uppercase 11/600/0.06em) so multiple cards line up
 *     and read as a coherent strip even at small widths.
 *   - 28/700 tabular-nums value — large enough to dominate the card but small
 *     enough to keep the strip dense; tabular-nums prevents number jitter.
 *   - Whole card is the click target when onClick is set; brand-tinted ring
 *     on hover replaces the old jumpy shadow.
 */
export const KpiCard = React.memo(function KpiCard({
  label,
  value,
  suffix,
  onClick,
}: {
  label: string;
  value: string | number;
  suffix?: string;
  onClick?: () => void;
}) {
  const isInteractive = Boolean(onClick);

  return (
    <button
      type={isInteractive ? 'button' : undefined}
      onClick={onClick}
      disabled={!isInteractive}
      className={[
        'flex w-full flex-col items-start rounded-2xl border border-slate-200 bg-white p-4 text-left',
        'shadow-(--shadow-xs) transition-all duration-150',
        'dark:border-slate-800 dark:bg-slate-900',
        isInteractive
          ? 'cursor-pointer hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20'
          : 'cursor-default',
      ].join(' ')}
    >
      <p className="text-overline text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-2 text-[28px] font-bold leading-none tracking-tight tabular-nums text-slate-900 dark:text-white">
        {value}
        {suffix && (
          <span className="ml-1.5 text-sm font-medium text-slate-400 dark:text-slate-500">
            {suffix}
          </span>
        )}
      </p>
    </button>
  );
});
