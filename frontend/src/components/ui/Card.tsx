import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function Card({ title, children, className = '', action }: CardProps) {
  return (
    <div
      className={`card-modern overflow-hidden ${className}`}
    >
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          {title && (
            <h3 className="text-[15px] font-semibold tracking-tight text-gray-900">{title}</h3>
          )}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}
