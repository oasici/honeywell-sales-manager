import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  /** Prefer this when passing action buttons; kept separate so nested
   *  sections that only want a description do not accidentally swallow
   *  unrelated children. */
  actions?: ReactNode;
  /** Legacy slot — still supported so older call sites keep working. */
  children?: ReactNode;
}

export function PageHeader({ title, description, actions, children }: PageHeaderProps) {
  const trailing = actions ?? children;
  return (
    <div className="mb-8 flex items-start justify-between animate-fade-in">
      <div>
        <h1 className="text-heading-1 text-gray-900 dark:text-white">{title}</h1>
        {description && (
          <p className="mt-1.5 text-body text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>
      {trailing && <div className="flex items-center gap-3">{trailing}</div>}
    </div>
  );
}
