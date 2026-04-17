import { useState, useEffect, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Wrench,
  Mail,
  Cog,
  FileText,
  Users,
  Settings,
  LogOut,
  ChevronRight,
  BarChart3,
  Kanban,
  TrendingUp,
  Target,
  ClipboardCheck,
  Radar,
  Brain,
  LayoutGrid,
  BookOpen,
  GraduationCap,
  MessageSquare,
  Shield,
  Plug,
  FormInput,
  KeyRound,
  Scale,
  Workflow,
  FilePenLine,
  Trophy,
  BarChart2,
  RefreshCw,
  FileCheck,
  Megaphone,
  ReceiptText,
  Map,
  GitBranch,
  Layers,
  AlertTriangle,
  ListChecks,
  Tag,
  UsersRound,
} from 'lucide-react';
import { approvalsApi } from '../../lib/api';

const COLLAPSE_KEY = 'sidebar-yedek-parca-collapsed';

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
  roles?: string[];
}

const yedekParcaItems: NavItem[] = [
  {
    label: 'nav.emails',
    to: '/emails',
    icon: <Mail size={18} className="shrink-0" />,
    roles: ['sales_rep', 'sales_manager'],
  },
  { label: 'nav.parts', to: '/parts', icon: <Cog size={18} className="shrink-0" /> },
  {
    label: 'nav.quotes',
    to: '/quotes',
    icon: <FileText size={18} className="shrink-0" />,
    roles: ['sales_rep', 'sales_manager'],
  },
  {
    label: 'nav.customers',
    to: '/customers',
    icon: <Users size={18} className="shrink-0" />,
    roles: ['sales_rep', 'sales_manager'],
  },
];

function filterByRole(items: NavItem[], role: string | undefined): NavItem[] {
  if (!role) return items;
  return items.filter((item) => !item.roles || item.roles.includes(role));
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-honeywell-red/10 text-honeywell-red'
      : 'text-gray-400 hover:bg-gray-800 hover:text-white'
  }`;
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
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

  const userRole = user?.role;
  const visibleYedekParcaItems = filterByRole(yedekParcaItems, userRole);
  const canSeeSettings = !userRole || ['sales_manager', 'operations'].includes(userRole);
  const canSeeReports = userRole === 'sales_manager';
  const canSeeApprovals = userRole === 'sales_rep' || userRole === 'sales_manager';

  const { data: pendingData } = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => approvalsApi.getPending(),
    enabled: canSeeApprovals,
    refetchInterval: 60_000,
  });
  const pendingCount = pendingData?.items?.length ?? 0;

  // Auto-expand if user navigates to a yedek parça route
  useEffect(() => {
    const isYedekParcaRoute = visibleYedekParcaItems.some((item) =>
      location.pathname.startsWith(item.to),
    );
    if (isYedekParcaRoute && collapsed) {
      queueMicrotask(() => setCollapsed(false));
    }
  }, [location.pathname, collapsed, visibleYedekParcaItems]);

  const t = useT();

  return (
    <aside className="flex h-screen w-64 flex-col bg-gradient-to-b from-gray-900 to-slate-900">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2.5 px-5 border-b border-white/5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-honeywell-red/10">
          <span className="text-sm font-black text-honeywell-red">H</span>
        </div>
        <div>
          <span className="text-sm font-bold text-white tracking-tight">Honeywell</span>
          <span className="ml-1.5 text-[10px] font-medium text-gray-500 uppercase tracking-widest">
            Sales
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {/* ── GENEL ── */}
        <NavLink to="/" end className={navLinkClass} onClick={onNavigate}>
          <LayoutDashboard size={18} className="shrink-0" />
          {t('nav.home')}
        </NavLink>

        {/* ── SATIS ── */}
        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <>
            <div className="pt-4 pb-1 px-3">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
                Satış
              </span>
            </div>
            <NavLink to="/cockpit" className={navLinkClass} onClick={onNavigate}>
              <Radar size={18} className="shrink-0" />
              Gelir Kokpiti
            </NavLink>
            <NavLink to="/board" className={navLinkClass} onClick={onNavigate}>
              <Kanban size={18} className="shrink-0" />
              Sales Board
            </NavLink>
          </>
        )}

        {userRole === 'sales_manager' && (
          <NavLink to="/sales-analytics" className={navLinkClass} onClick={onNavigate}>
            <TrendingUp size={18} className="shrink-0" />
            Satış Analitiği
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/leads" className={navLinkClass} onClick={onNavigate}>
            <Target size={18} className="shrink-0" />
            Potansiyel Müşteriler
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/subscriptions" className={navLinkClass} onClick={onNavigate}>
            <RefreshCw size={18} className="shrink-0" />
            Abonelikler
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/contracts" className={navLinkClass} onClick={onNavigate}>
            <FileCheck size={18} className="shrink-0" />
            Kontratlar
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/campaigns" className={navLinkClass} onClick={onNavigate}>
            <Megaphone size={18} className="shrink-0" />
            Kampanyalar
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/invoices" className={navLinkClass} onClick={onNavigate}>
            <ReceiptText size={18} className="shrink-0" />
            Faturalar
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/revenue-recognition" className={navLinkClass} onClick={onNavigate}>
            <TrendingUp size={18} className="shrink-0" />
            Gelir Tanıma
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/at-risk" className={navLinkClass} onClick={onNavigate}>
            <AlertTriangle size={18} className="shrink-0" />
            Riskli Fırsatlar
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/leaderboard" className={navLinkClass} onClick={onNavigate}>
            <Trophy size={18} className="shrink-0" />
            Sıralama
          </NavLink>
        )}

        {canSeeApprovals && (
          <NavLink to="/approvals" className={navLinkClass} onClick={onNavigate}>
            <ClipboardCheck size={18} className="shrink-0" />
            <span className="flex-1">Onaylar</span>
            {pendingCount > 0 && (
              <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-honeywell-red px-1.5 text-[10px] font-bold text-white">
                {pendingCount}
              </span>
            )}
          </NavLink>
        )}

        {/* Yedek Parça collapsible section */}
        <div>
          <button
            onClick={() => setCollapsed((c: boolean) => !c)}
            aria-expanded={!collapsed}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-3">
              <Wrench size={18} className="shrink-0" />
              {t('nav.spare_parts')}
            </span>
            <ChevronRight
              size={16}
              className={`shrink-0 transition-transform ${collapsed ? '' : 'rotate-90'}`}
            />
          </button>

          {!collapsed && (
            <div className="ml-4 mt-1 space-y-1">
              {visibleYedekParcaItems.map((item) => (
                <NavLink key={item.to} to={item.to} className={navLinkClass} onClick={onNavigate}>
                  {item.icon}
                  {t(item.label as Parameters<typeof t>[0])}
                </NavLink>
              ))}
            </div>
          )}
        </div>

        {/* ── ARACLAR ── */}
        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <>
            <div className="pt-4 pb-1 px-3">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
                Araclar
              </span>
            </div>
            <NavLink to="/ai/insights" className={navLinkClass} onClick={onNavigate}>
              <Brain size={18} className="shrink-0" />
              AI Asistan
            </NavLink>
            <NavLink to="/email-templates" className={navLinkClass} onClick={onNavigate}>
              <FilePenLine size={18} className="shrink-0" />
              Email Şablonları
            </NavLink>
            <NavLink to="/dashboards" className={navLinkClass} onClick={onNavigate}>
              <LayoutGrid size={18} className="shrink-0" />
              Panolar
            </NavLink>
          </>
        )}

        {/* Oyun Planlari - manager only */}
        {userRole === 'sales_manager' && (
          <NavLink to="/playbooks" className={navLinkClass} onClick={onNavigate}>
            <BookOpen size={18} className="shrink-0" />
            Oyun Planlari
          </NavLink>
        )}

        {/* Koçluk - manager only */}
        {userRole === 'sales_manager' && (
          <NavLink to="/coaching" className={navLinkClass} onClick={onNavigate}>
            <GraduationCap size={18} className="shrink-0" />
            Koçluk
          </NavLink>
        )}

        {/* Etkileşim - sales roles */}
        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <>
            <NavLink to="/engagement/transcripts" className={navLinkClass} onClick={onNavigate}>
              <MessageSquare size={18} className="shrink-0" />
              Görüşmeler
            </NavLink>
            <NavLink to="/engagement/keywords" className={navLinkClass} onClick={onNavigate}>
              <Tag size={18} className="shrink-0" />
              Anahtar Kelimeler
            </NavLink>
            <NavLink to="/engagement/sequences" className={navLinkClass} onClick={onNavigate}>
              <ListChecks size={18} className="shrink-0" />
              Sekanslar
            </NavLink>
            <NavLink to="/engagement/segments" className={navLinkClass} onClick={onNavigate}>
              <UsersRound size={18} className="shrink-0" />
              Segmentler
            </NavLink>
          </>
        )}

        {/* Settings */}
        {canSeeSettings && (
          <NavLink to="/settings" className={navLinkClass} onClick={onNavigate}>
            <Settings size={18} className="shrink-0" />
            {t('nav.settings')}
          </NavLink>
        )}

        {/* Pipeline Settings */}
        {canSeeSettings && (
          <NavLink to="/settings/pipelines" className={navLinkClass} onClick={onNavigate}>
            <GitBranch size={18} className="shrink-0" />
            Pipeline Ayarlari
          </NavLink>
        )}

        {/* Reports - sales_manager only */}
        {canSeeReports && (
          <NavLink to="/reports/saved" className={navLinkClass} onClick={onNavigate}>
            <BarChart3 size={18} className="shrink-0" />
            Raporlar
          </NavLink>
        )}

        {/* KVKK Uyum - manager & operations */}
        {(userRole === 'sales_manager' || userRole === 'operations') && (
          <NavLink to="/compliance" className={navLinkClass} onClick={onNavigate}>
            <Shield size={18} className="shrink-0" />
            KVKK Uyum
          </NavLink>
        )}

        {/* Entegrasyonlar - manager only */}
        {userRole === 'sales_manager' && (
          <NavLink to="/integrations" className={navLinkClass} onClick={onNavigate}>
            <Plug size={18} className="shrink-0" />
            Entegrasyonlar
          </NavLink>
        )}

        {/* ── YONETIM ── */}
        {userRole === 'sales_manager' && (
          <>
            <div className="pt-4 pb-1 px-3">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
                Yönetim
              </span>
            </div>
            <NavLink to="/admin/custom-fields" className={navLinkClass} onClick={onNavigate}>
              <FormInput size={18} className="shrink-0" />
              Özel Alanlar
            </NavLink>
            <NavLink to="/admin/field-permissions" className={navLinkClass} onClick={onNavigate}>
              <KeyRound size={18} className="shrink-0" />
              Alan İzinleri
            </NavLink>
            <NavLink to="/admin/product-rules" className={navLinkClass} onClick={onNavigate}>
              <Scale size={18} className="shrink-0" />
              Ürün Kuralları
            </NavLink>
            <NavLink to="/admin/workflow-rules" className={navLinkClass} onClick={onNavigate}>
              <Workflow size={18} className="shrink-0" />
              İş Kuralları
            </NavLink>
            <NavLink to="/admin/data-quality" className={navLinkClass} onClick={onNavigate}>
              <BarChart2 size={18} className="shrink-0" />
              Veri Kalitesi
            </NavLink>
            <NavLink to="/admin/territories" className={navLinkClass} onClick={onNavigate}>
              <Map size={18} className="shrink-0" />
              Bölge Yönetimi
            </NavLink>
            <NavLink to="/admin/pricing" className={navLinkClass} onClick={onNavigate}>
              <Layers size={18} className="shrink-0" />
              Fiyatlama Yönetimi
            </NavLink>
            <NavLink to="/admin/chat" className={navLinkClass} onClick={onNavigate}>
              <MessageSquare size={18} className="shrink-0" />
              Canlı Sohbet
            </NavLink>
          </>
        )}
      </nav>

      {/* User info at bottom */}
      <div className="border-t border-gray-800 px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">
              {user?.full_name || 'Kullanıcı'}
            </p>
            <p className="truncate text-xs text-gray-400">{user?.email || ''}</p>
          </div>
          <button
            onClick={handleLogout}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
            aria-label="Çıkış Yap"
            title="Çıkış Yap"
          >
            <LogOut size={20} className="shrink-0" />
          </button>
        </div>
      </div>
    </aside>
  );
}
