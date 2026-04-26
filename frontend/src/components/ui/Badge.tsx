import type { ReactNode } from 'react';

/**
 * Badge — small status pill.
 *
 * Variants:
 *   default   neutral slate, for tags / non-status labels
 *   success   green — closed-won, completed, healthy
 *   warning   amber — pending, at-risk, action-needed
 *   danger    red — failed, churned, blocked
 *   info      blue — informational ("new", "draft")
 *
 * Sizes:
 *   sm  20px high — table rows, compact chips
 *   md  24px high — default; cards, list items
 *
 * Visual:
 *   - Soft background tint + matching ring (1px inset) for definition
 *   - Mono-weight text (font-medium 500) for legibility at small sizes
 *   - All variants use the same horizontal padding for perfect column alignment
 */
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'default';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  variant?: BadgeVariant;
  size?: BadgeSize;
  children: ReactNode;
  className?: string;
  title?: string;
  /** Adds a small leading dot (status indicator pattern). */
  dot?: boolean;
}

const variantClasses: Record<BadgeVariant, string> = {
  default:
    'bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
  success:
    'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900',
  warning:
    'bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900',
  danger:
    'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900',
  info:
    'bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-900',
};

const dotClasses: Record<BadgeVariant, string> = {
  default: 'bg-slate-400',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger: 'bg-red-500',
  info: 'bg-blue-500',
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: 'h-5 px-2 text-[11px] gap-1',
  md: 'h-6 px-2.5 text-xs gap-1.5',
};

export function Badge({
  variant = 'default',
  size = 'md',
  children,
  className = '',
  title,
  dot = false,
}: BadgeProps) {
  return (
    <span
      title={title}
      className={[
        'inline-flex items-center justify-center rounded-full font-medium whitespace-nowrap',
        variantClasses[variant],
        sizeClasses[size],
        className,
      ].join(' ')}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dotClasses[variant]}`} />}
      {children}
    </span>
  );
}
