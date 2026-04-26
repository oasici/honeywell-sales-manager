import type { ReactNode } from 'react';

/**
 * Card — primary content surface.
 *
 * Visual:
 *   - 16px radius, 1px slate-200 border, --shadow-xs (barely visible)
 *   - hover: shadow promotes to --shadow-sm; interactive cards get a darker border
 *   - content padding 24px (px-6 py-5); header has bottom divider
 *
 * Use:
 *   <Card title="Title" description="Optional sub" action={<Button/>}>...</Card>
 *   <Card interactive onClick={...}>...</Card>     // for whole-card click
 *   <Card padding="none">...</Card>                // for tables, custom layout
 */
interface CardProps {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
  /** Removes inner padding so consumers can render flush layouts (tables, lists). */
  padding?: 'default' | 'none';
  /** Adds hover affordance + cursor pointer; pair with onClick. */
  interactive?: boolean;
  onClick?: () => void;
}

export function Card({
  title,
  description,
  children,
  className = '',
  action,
  padding = 'default',
  interactive = false,
  onClick,
}: CardProps) {
  const interactiveClass = interactive ? 'is-interactive' : '';
  const Tag = interactive && onClick ? 'button' : 'div';

  return (
    <Tag
      onClick={onClick}
      type={Tag === 'button' ? 'button' : undefined}
      className={[
        'card-modern overflow-hidden animate-fade-in w-full text-left',
        interactiveClass,
        className,
      ].join(' ')}
    >
      {(title || action) && (
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="min-w-0">
            {title && (
              <h3 className="text-heading-3 text-slate-900 dark:text-white">{title}</h3>
            )}
            {description && (
              <p className="mt-0.5 text-caption text-slate-500 dark:text-slate-400">
                {description}
              </p>
            )}
          </div>
          {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={padding === 'none' ? '' : 'px-6 py-5'}>{children}</div>
    </Tag>
  );
}
