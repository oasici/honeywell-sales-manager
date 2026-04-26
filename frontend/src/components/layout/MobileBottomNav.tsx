import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Kanban, Target, FileText, Menu } from 'lucide-react';

/**
 * MobileBottomNav — sticky bottom rail shown only under lg.
 *
 * Visual:
 *   - 56px row + safe-area inset; matches iOS/Android tab-bar standards.
 *   - Active tab: brand red icon + label, plus a 3px brand-tinted "ink" pill
 *     under the icon to make the active state legible without color alone.
 *   - Inactive: slate-500 icon, slate-600 label — readable but quiet.
 *   - Border-top hairline on slate-200; surface stays white so the row reads
 *     as part of the page chrome rather than a floating overlay.
 */
interface NavItem {
  label: string;
  to: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Panel', to: '/', icon: LayoutDashboard },
  { label: 'Board', to: '/board', icon: Kanban },
  { label: 'Leadler', to: '/leads', icon: Target },
  { label: 'Teklifler', to: '/quotes', icon: FileText },
  { label: 'Menü', to: '/settings', icon: Menu },
];

export function MobileBottomNav() {
  const location = useLocation();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 block border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] shadow-(--shadow-sm) lg:hidden dark:border-slate-800 dark:bg-slate-950"
      aria-label="Alt menü"
    >
      <div className="flex items-stretch justify-around px-1 py-1.5">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to);
          const Icon = item.icon;

          return (
            <NavLink
              key={item.to}
              to={item.to}
              aria-current={isActive ? 'page' : undefined}
              className={[
                'group relative flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[10px] font-medium transition-colors',
                isActive
                  ? 'text-honeywell-red'
                  : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200',
              ].join(' ')}
            >
              {/* Active indicator pill — sits at the top edge so the icon
                  becomes the visual anchor; uses brand red at 100%. */}
              <span
                aria-hidden
                className={[
                  'absolute -top-1.5 h-[3px] w-8 rounded-full transition-opacity',
                  isActive ? 'bg-honeywell-red opacity-100' : 'opacity-0',
                ].join(' ')}
              />
              <Icon
                size={20}
                strokeWidth={isActive ? 2.25 : 1.75}
                className="shrink-0"
                aria-hidden
              />
              <span className="leading-tight">{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
