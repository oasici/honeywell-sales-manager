import type { ReactNode } from 'react';

/**
 * PageHeader — the top of every routed page.
 *
 * Visual:
 *   - Title: text-heading-1 (32/40 700 -0.02em) — significantly larger than
 *     section headings so the page anchor is unambiguous.
 *   - Description: text-body (14/22 400) slate-500, max 60ch for readability.
 *   - Right slot: action buttons; aligned to title baseline so the row reads
 *     as a single visual unit.
 *
 * Spacing:
 *   - mb-8 below the header — gives content "room to breathe" before
 *     KPI cards / filters / tables. Don't compact this; the visual rest is
 *     what makes the next section feel intentional.
 */
interface PageHeaderProps {
  title: string;
  description?: string;
  /** Right-side action slot — buttons, dropdowns. */
  children?: ReactNode;
  /** Optional eyebrow above the title (e.g. "Yönetim ›"). */
  eyebrow?: string;
}

export function PageHeader({ title, description, children, eyebrow }: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-col items-start justify-between gap-4 animate-fade-in sm:flex-row sm:items-end">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-overline text-slate-500 dark:text-slate-400">{eyebrow}</p>
        )}
        <h1 className="text-heading-1 text-slate-900 dark:text-white">{title}</h1>
        {description && (
          <p className="mt-2 max-w-[60ch] text-body text-slate-500 dark:text-slate-400">
            {description}
          </p>
        )}
      </div>
      {children && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>
      )}
    </div>
  );
}
