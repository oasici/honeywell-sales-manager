import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  children?: ReactNode;
}

export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <div className="mb-8 flex items-start justify-between animate-fade-in">
      <div>
        <h1 className="text-heading-1 text-gray-900 dark:text-white">{title}</h1>
        {description && (
          <p className="mt-1.5 text-body text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>
      {children && <div className="flex items-center gap-3">{children}</div>}
    </div>
  );
}
