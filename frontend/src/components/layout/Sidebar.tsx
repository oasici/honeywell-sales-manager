import { useState, useEffect, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { LayoutDashboard, Wrench, Mail, Cog, FileText, Users, Settings, LogOut, ChevronRight } from 'lucide-react';

const COLLAPSE_KEY = 'sidebar-yedek-parca-collapsed';

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
}

const yedekParcaItems: NavItem[] = [
  { label: 'Mailler', to: '/emails', icon: <Mail size={18} className="shrink-0" /> },
  { label: 'Parcalar', to: '/parts', icon: <Cog size={18} className="shrink-0" /> },
  { label: 'Teklifler', to: '/quotes', icon: <FileText size={18} className="shrink-0" /> },
  { label: 'Musteriler', to: '/customers', icon: <Users size={18} className="shrink-0" /> },
];

function navLinkClass({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-honeywell-red/10 text-honeywell-red'
      : 'text-gray-400 hover:bg-gray-800 hover:text-white'
  }`;
}

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const [collapsed, setCollapsed] = useState(() => {
    const saved = localStorage.getItem(COLLAPSE_KEY);
    return saved ? JSON.parse(saved) : false;
  });

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify(collapsed));
  }, [collapsed]);

  // Auto-expand if user navigates to a yedek parca route
  useEffect(() => {
    const isYedekParcaRoute = yedekParcaItems.some((item) =>
      location.pathname.startsWith(item.to),
    );
    if (isYedekParcaRoute && collapsed) {
      setCollapsed(false);
    }
  }, [location.pathname]);

  return (
    <aside className="flex h-screen w-64 flex-col bg-gray-900">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2 px-5">
        <span className="text-lg font-bold text-honeywell-red">Honeywell</span>
        <span className="text-xs font-medium text-gray-500 mt-0.5">Sales Suit</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {/* Dashboard */}
        <NavLink to="/" end className={navLinkClass}>
          <LayoutDashboard size={18} className="shrink-0" />
          Ana Sayfa
        </NavLink>

        {/* Yedek Parca collapsible section */}
        <div>
          <button
            onClick={() => setCollapsed((c: boolean) => !c)}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
          >
            <span className="flex items-center gap-3">
              <Wrench size={18} className="shrink-0" />
              Yedek Parca
            </span>
            <ChevronRight size={16} className={`shrink-0 transition-transform ${collapsed ? '' : 'rotate-90'}`} />
          </button>

          {!collapsed && (
            <div className="ml-4 mt-1 space-y-1">
              {yedekParcaItems.map((item) => (
                <NavLink key={item.to} to={item.to} className={navLinkClass}>
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
            </div>
          )}
        </div>

        {/* Ayarlar */}
        <NavLink to="/settings" className={navLinkClass}>
          <Settings size={18} className="shrink-0" />
          Ayarlar
        </NavLink>
      </nav>

      {/* User info at bottom */}
      <div className="border-t border-gray-800 px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">{user?.full_name || 'Kullanici'}</p>
            <p className="truncate text-xs text-gray-400">{user?.email || ''}</p>
          </div>
          <button
            onClick={handleLogout}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
            title="Cikis Yap"
          >
            <LogOut size={20} className="shrink-0" />
          </button>
        </div>
      </div>
    </aside>
  );
}
