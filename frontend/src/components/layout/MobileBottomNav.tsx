import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Kanban, Target, FileText, Menu } from 'lucide-react';

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
  { label: 'Menu', to: '/settings', icon: Menu },
];

function navItemClass(isActive: boolean): string {
  return `flex flex-col items-center gap-0.5 text-[10px] font-medium transition-colors ${
    isActive ? 'text-honeywell-red' : 'text-gray-400'
  }`;
}

export function MobileBottomNav() {
  const location = useLocation();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 block lg:hidden border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900 pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-center justify-around px-2 py-2">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.to);

          const Icon = item.icon;

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={() => navItemClass(isActive)}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 2} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
