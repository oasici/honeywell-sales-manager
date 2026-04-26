/**
 * Skeleton — loading placeholders aligned to the design system.
 *
 * Variants:
 *   - line: stack of 3 short bars (default)
 *   - card: 2xl card with title + body lines
 *   - table: 2xl table shell with header + 3 rows
 *
 * When `className` is provided we render a single shimmer block — useful for
 * one-off shapes (e.g. KPI tiles, chart placeholders, avatars).
 */
interface SkeletonProps {
  variant?: 'line' | 'card' | 'table';
  count?: number;
  className?: string;
}

const SHIMMER = 'animate-pulse rounded bg-slate-200/80 dark:bg-slate-800';

function SkeletonLine() {
  return <div className={`h-4 w-full ${SHIMMER}`} />;
}

function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div className={`mb-4 h-3 w-1/3 ${SHIMMER}`} />
      <div className="space-y-2.5">
        <div className={`h-3 w-full ${SHIMMER}`} />
        <div className={`h-3 w-5/6 ${SHIMMER}`} />
        <div className={`h-3 w-4/6 ${SHIMMER}`} />
      </div>
    </div>
  );
}

function SkeletonTable() {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex gap-4 border-b border-slate-200 bg-slate-50/60 px-6 py-3 dark:border-slate-800 dark:bg-slate-900/40">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`h-2.5 w-1/4 max-w-[120px] ${SHIMMER}`} />
        ))}
      </div>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="flex gap-4 border-b border-slate-100 px-6 py-4 last:border-b-0 dark:border-slate-800"
        >
          {[0, 1, 2, 3].map((j) => (
            <div key={j} className={`h-3 w-1/4 max-w-[180px] ${SHIMMER}`} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Skeleton({ variant = 'line', count = 1, className }: SkeletonProps) {
  if (className) {
    return <div className={`animate-pulse bg-slate-200/80 dark:bg-slate-800 ${className}`} />;
  }
  const items = Array.from({ length: count }, (_, i) => i);

  if (variant === 'card') {
    return (
      <div className="space-y-4">
        {items.map((i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (variant === 'table') {
    return (
      <div className="space-y-4">
        {items.map((i) => (
          <SkeletonTable key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((i) => (
        <SkeletonLine key={i} />
      ))}
    </div>
  );
}
