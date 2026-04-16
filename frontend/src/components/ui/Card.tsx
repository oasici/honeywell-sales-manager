import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function Card({ title, children, className = '', action }: CardProps) {
  return (
    <div className={`card-modern overflow-hidden animate-fade-in ${className}`}>
      {(title || action) && (
        <div
          className="flex items-center justify-between border-b px-6 py-4"
          style={{ borderColor: 'var(--border-light)' }}
        >
          {title && <h3 className="text-heading-3 text-gray-900 dark:text-white">{title}</h3>}
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}
