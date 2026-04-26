import type { ReactNode } from 'react';

/**
 * EmptyState — premium "nothing here yet" pattern.
 *
 * Visual:
 *   - Icon sits in a 56×56 rounded slate-50 container (gives it weight)
 *   - Title: 18/600 slate-900
 *   - Description: 14/400 slate-500, max 360px so lines stay readable
 *   - Action: any node (typically Button); centered with mt-6
 *
 * Use this whenever a list/table/board returns 0 results. The product looks
 * unfinished without it — a bare "Kayıt yok" centered string reads as a
 * loading bug to most users.
 */
interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  /** Smaller variant for use inside cards (no border container, less padding). */
  variant?: 'default' | 'compact';
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  variant = 'default',
}: EmptyStateProps) {
  const isCompact = variant === 'compact';

  return (
    <div
      className={[
        'flex flex-col items-center justify-center text-center',
        isCompact ? 'py-10' : 'py-16',
      ].join(' ')}
    >
      {icon && (
        <div
          className={[
            'mb-4 inline-flex items-center justify-center rounded-2xl',
            'bg-slate-50 text-slate-400 ring-1 ring-inset ring-slate-100',
            'dark:bg-slate-800/50 dark:text-slate-500 dark:ring-slate-800',
            isCompact ? 'h-12 w-12' : 'h-14 w-14',
          ].join(' ')}
        >
          {icon}
        </div>
      )}
      <h3 className="text-heading-3 text-slate-900 dark:text-slate-100">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-[360px] text-body text-slate-500 dark:text-slate-400">
          {description}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
