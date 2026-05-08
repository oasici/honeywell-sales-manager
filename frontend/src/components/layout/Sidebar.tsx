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
  ListFilter,
  Tag,
  UsersRound,
  Database,
  History,
  Activity,
  ListTree,
  LineChart,
  Network as NetworkIcon,
  Sparkles,
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
    label: 'nav.parts_intel',
    to: '/parts-intel',
    icon: <Cog size={18} className="shrink-0" />,
    roles: ['sales_manager', 'operations'],
  },
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
  {
    label: 'nav.high_intent',
    to: '/customers/high-intent',
    icon: <Target size={18} className="shrink-0" />,
    roles: ['sales_rep', 'sales_manager'],
  },
];

function filterByRole(items: NavItem[], role: string | undefined): NavItem[] {
  if (!role) return items;
  return items.filter((item) => !item.roles || item.roles.includes(role));
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  // Linear-style sidebar items: 8px radius, calmer hover (white/5 not gray-800),
  // active state uses brand red tint at 12% with red text + 1px ring for definition.
  return [
    'flex items-center gap-3 h-9 rounded-[10px] px-3 text-[13px] font-medium',
    'transition-[background-color,color] duration-150',
    isActive
      ? 'bg-honeywell-red/12 text-white ring-1 ring-honeywell-red/20'
      : 'text-slate-400 hover:bg-white/4 hover:text-slate-100',
  ].join(' ');
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
  // Audit + KVKK export gate. The backend endpoints require
  // SALES_MANAGER specifically (operations gets 403), so showing
  // these links to operations users used to surface a confusing
  // "Beklenmeyen bir hata oluştu" toast when they clicked through.
  const canSeeAudit = userRole === 'sales_manager';

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
    <aside className="flex h-screen w-[260px] flex-col bg-slate-950 border-r border-white/6">
      {/* Brand block — calmer; the H mark gets a softer red wash */}
      <div className="flex h-[60px] items-center gap-2.5 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-honeywell-red/12 ring-1 ring-honeywell-red/20">
          <span className="text-sm font-bold text-honeywell-red leading-none">H</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-sm font-semibold text-white tracking-tight">Honeywell</span>
          <span className="text-[10px] font-medium text-slate-500 uppercase tracking-[0.15em]">
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
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                {t('nav.section_sales')}
              </span>
            </div>
            <NavLink to="/cockpit" className={navLinkClass} onClick={onNavigate}>
              <Radar size={18} className="shrink-0" />
              {t('nav.cockpit')}
            </NavLink>
            {/* Round-8 R8-NAV-1/2 — manager-only views. Forecast endpoints
                require SALES_MANAGER role; network intelligence is restricted
                to managers per the page docstring. */}
            {userRole === 'sales_manager' && (
              <>
                <NavLink to="/forecast" className={navLinkClass} onClick={onNavigate}>
                  <LineChart size={18} className="shrink-0" />
                  {t('nav.forecast')}
                </NavLink>
                <NavLink to="/network-intelligence" className={navLinkClass} onClick={onNavigate}>
                  <NetworkIcon size={18} className="shrink-0" />
                  {t('nav.network_intelligence')}
                </NavLink>
              </>
            )}
            <NavLink to="/board" className={navLinkClass} onClick={onNavigate}>
              <Kanban size={18} className="shrink-0" />
              {t('nav.board')}
            </NavLink>
            <NavLink to="/opportunities" className={navLinkClass} onClick={onNavigate}>
              <Layers size={18} className="shrink-0" />
              {t('nav.opportunities')}
            </NavLink>
            <NavLink to="/planning-studio" className={navLinkClass} onClick={onNavigate}>
              <ListFilter size={18} className="shrink-0" />
              {t('nav.planning_studio')}
            </NavLink>
          </>
        )}

        {userRole === 'sales_manager' && (
          <NavLink to="/sales-analytics" className={navLinkClass} onClick={onNavigate}>
            <TrendingUp size={18} className="shrink-0" />
            {t('nav.sales_analytics')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/leads" className={navLinkClass} onClick={onNavigate}>
            <Target size={18} className="shrink-0" />
            {t('nav.leads')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/subscriptions" className={navLinkClass} onClick={onNavigate}>
            <RefreshCw size={18} className="shrink-0" />
            {t('nav.subscriptions')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/contracts" className={navLinkClass} onClick={onNavigate}>
            <FileCheck size={18} className="shrink-0" />
            {t('nav.contracts')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/campaigns" className={navLinkClass} onClick={onNavigate}>
            <Megaphone size={18} className="shrink-0" />
            {t('nav.campaigns')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/invoices" className={navLinkClass} onClick={onNavigate}>
            <ReceiptText size={18} className="shrink-0" />
            {t('nav.invoices')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/revenue-recognition" className={navLinkClass} onClick={onNavigate}>
            <TrendingUp size={18} className="shrink-0" />
            {t('nav.revenue_recognition')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/at-risk" className={navLinkClass} onClick={onNavigate}>
            <AlertTriangle size={18} className="shrink-0" />
            {t('nav.at_risk')}
          </NavLink>
        )}

        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <NavLink to="/leaderboard" className={navLinkClass} onClick={onNavigate}>
            <Trophy size={18} className="shrink-0" />
            {t('nav.leaderboard')}
          </NavLink>
        )}

        {canSeeApprovals && (
          <NavLink to="/approvals" className={navLinkClass} onClick={onNavigate}>
            <ClipboardCheck size={18} className="shrink-0" />
            <span className="flex-1">{t('nav.approvals')}</span>
            {pendingCount > 0 && (
              <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-honeywell-red px-1.5 text-[10px] font-bold text-white">
                {pendingCount}
              </span>
            )}
          </NavLink>
        )}
        {/* R6-NAV-1 — /approvals/rules was routed but never linked.
            R7-I18N-2 — i18n key now wired. */}
        {userRole === 'sales_manager' && (
          <NavLink to="/approvals/rules" className={navLinkClass} onClick={onNavigate}>
            <Workflow size={18} className="shrink-0" />
            {t('nav.approval_rules')}
          </NavLink>
        )}

        {/* Yedek Parça collapsible section */}
        <div>
          <button
            onClick={() => setCollapsed((c: boolean) => !c)}
            aria-expanded={!collapsed}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium text-slate-400 hover:bg-gray-800 hover:text-white transition-colors cursor-pointer"
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
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                {t('nav.section_tools')}
              </span>
            </div>
            <NavLink to="/ai/insights" className={navLinkClass} onClick={onNavigate}>
              <Brain size={18} className="shrink-0" />
              {t('nav.ai_assistant')}
            </NavLink>
            {/* R6-NAV-1 — /ai/tasks routed but absent from sidebar.
                R7-I18N-2 — i18n key now wired. */}
            <NavLink to="/ai/tasks" className={navLinkClass} onClick={onNavigate}>
              <ListChecks size={18} className="shrink-0" />
              {t('nav.ai_tasks')}
            </NavLink>
            <NavLink to="/insights" className={navLinkClass} onClick={onNavigate}>
              <TrendingUp size={18} className="shrink-0" />
              {t('nav.insights')}
            </NavLink>
            {/* R6-NAV-1 — Report Builder routed but never surfaced.
                R7-I18N-2 — i18n key now wired. */}
            {userRole === 'sales_manager' && (
              <NavLink to="/reports/builder" className={navLinkClass} onClick={onNavigate}>
                <BarChart3 size={18} className="shrink-0" />
                {t('nav.report_builder')}
              </NavLink>
            )}
            <NavLink to="/email-templates" className={navLinkClass} onClick={onNavigate}>
              <FilePenLine size={18} className="shrink-0" />
              {t('nav.email_templates')}
            </NavLink>
            <NavLink to="/dashboards" className={navLinkClass} onClick={onNavigate}>
              <LayoutGrid size={18} className="shrink-0" />
              {t('nav.dashboards')}
            </NavLink>
          </>
        )}

        {/* Oyun Planlari - manager only */}
        {userRole === 'sales_manager' && (
          <>
            <NavLink to="/playbooks" className={navLinkClass} onClick={onNavigate}>
              <BookOpen size={18} className="shrink-0" />
              {t('nav.playbooks')}
            </NavLink>
            {/* R6-NAV-1 — /playbooks/templates and /playbooks/analytics
                were routed but never linked. */}
            <NavLink to="/playbooks/templates" className={navLinkClass} onClick={onNavigate}>
              <FileText size={18} className="shrink-0" />
              {t('nav.playbook_templates')}
            </NavLink>
            <NavLink to="/playbooks/analytics" className={navLinkClass} onClick={onNavigate}>
              <BarChart2 size={18} className="shrink-0" />
              {t('nav.playbook_analytics')}
            </NavLink>
          </>
        )}

        {/* Koçluk - manager only */}
        {userRole === 'sales_manager' && (
          <NavLink to="/coaching" className={navLinkClass} onClick={onNavigate}>
            <GraduationCap size={18} className="shrink-0" />
            {t('nav.coaching')}
          </NavLink>
        )}

        {/* Etkileşim - sales roles */}
        {(userRole === 'sales_rep' || userRole === 'sales_manager') && (
          <>
            <NavLink to="/engagement/transcripts" className={navLinkClass} onClick={onNavigate}>
              <MessageSquare size={18} className="shrink-0" />
              {t('nav.transcripts')}
            </NavLink>
            <NavLink to="/engagement/keywords" className={navLinkClass} onClick={onNavigate}>
              <Tag size={18} className="shrink-0" />
              {t('nav.keywords')}
            </NavLink>
            <NavLink to="/engagement/sequences" className={navLinkClass} onClick={onNavigate}>
              <ListChecks size={18} className="shrink-0" />
              {t('nav.sequences')}
            </NavLink>
            <NavLink to="/engagement/segments" className={navLinkClass} onClick={onNavigate}>
              <UsersRound size={18} className="shrink-0" />
              {t('nav.segments')}
            </NavLink>
            {/* R6-NAV-1 — /engagement/scorecards routed but never linked. */}
            <NavLink to="/engagement/scorecards" className={navLinkClass} onClick={onNavigate}>
              <Trophy size={18} className="shrink-0" />
              {t('nav.scorecards')}
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
            {t('nav.pipeline_settings')}
          </NavLink>
        )}

        {/* Reports - sales_manager only */}
        {canSeeReports && (
          <NavLink to="/reports/saved" className={navLinkClass} onClick={onNavigate}>
            <BarChart3 size={18} className="shrink-0" />
            {t('nav.reports')}
          </NavLink>
        )}

        {/* KVKK Uyum - manager & operations */}
        {(userRole === 'sales_manager' || userRole === 'operations') && (
          <NavLink to="/compliance" className={navLinkClass} onClick={onNavigate}>
            <Shield size={18} className="shrink-0" />
            {t('nav.compliance')}
          </NavLink>
        )}
        {/* R6-NAV-1 — /compliance/retention and /compliance/breaches
            were routed but never linked. Both are KVKK-mandated tools
            that need first-class navigation. */}
        {(userRole === 'sales_manager' || userRole === 'operations') && (
          <>
            <NavLink to="/compliance/retention" className={navLinkClass} onClick={onNavigate}>
              <Database size={18} className="shrink-0" />
              {t('nav.retention')}
            </NavLink>
            <NavLink to="/compliance/breaches" className={navLinkClass} onClick={onNavigate}>
              <AlertTriangle size={18} className="shrink-0" />
              {t('nav.breaches')}
            </NavLink>
          </>
        )}

        {/* Entegrasyonlar - manager only */}
        {userRole === 'sales_manager' && (
          <NavLink to="/integrations" className={navLinkClass} onClick={onNavigate}>
            <Plug size={18} className="shrink-0" />
            {t('nav.integrations')}
          </NavLink>
        )}

        {/* ── YONETIM ── */}
        {userRole === 'sales_manager' && (
          <>
            <div className="pt-4 pb-1 px-3">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                {t('nav.section_admin')}
              </span>
            </div>
            <NavLink to="/admin/custom-fields" className={navLinkClass} onClick={onNavigate}>
              <FormInput size={18} className="shrink-0" />
              {t('nav.custom_fields')}
            </NavLink>
            <NavLink to="/admin/ai-attributes" className={navLinkClass} onClick={onNavigate}>
              <Sparkles size={18} className="shrink-0" />
              {t('nav.ai_attributes')}
            </NavLink>
            <NavLink to="/admin/field-permissions" className={navLinkClass} onClick={onNavigate}>
              <KeyRound size={18} className="shrink-0" />
              {t('nav.field_permissions')}
            </NavLink>
            <NavLink to="/admin/product-rules" className={navLinkClass} onClick={onNavigate}>
              <Scale size={18} className="shrink-0" />
              {t('nav.product_rules')}
            </NavLink>
            <NavLink to="/admin/workflow-rules" className={navLinkClass} onClick={onNavigate}>
              <Workflow size={18} className="shrink-0" />
              {t('nav.workflow_rules')}
            </NavLink>
            <NavLink to="/admin/data-quality" className={navLinkClass} onClick={onNavigate}>
              <BarChart2 size={18} className="shrink-0" />
              {t('nav.data_quality')}
            </NavLink>
            <NavLink to="/admin/territories" className={navLinkClass} onClick={onNavigate}>
              <Map size={18} className="shrink-0" />
              {t('nav.territories')}
            </NavLink>
            <NavLink to="/admin/pricing" className={navLinkClass} onClick={onNavigate}>
              <Layers size={18} className="shrink-0" />
              {t('nav.pricing_admin')}
            </NavLink>
            <NavLink to="/admin/chat" className={navLinkClass} onClick={onNavigate}>
              <MessageSquare size={18} className="shrink-0" />
              {t('nav.live_chat')}
            </NavLink>
            {/* R7-NAV-1 — /users was orphaned (managers had to type the
                URL). Manager-only entry into the user-management surface. */}
            {userRole === 'sales_manager' && (
              <NavLink to="/users" className={navLinkClass} onClick={onNavigate}>
                <UsersRound size={18} className="shrink-0" />
                {t('nav.user_management')}
              </NavLink>
            )}
            {/* R7-NAV-2 — /reports legacy ReportsPage lived without a
                NavLink, only reachable by URL guess. */}
            {userRole === 'sales_manager' && (
              <NavLink to="/reports" className={navLinkClass} onClick={onNavigate}>
                <FileText size={18} className="shrink-0" />
                {t('nav.reports_legacy')}
              </NavLink>
            )}
            {canSeeAudit && (
              <>
                <NavLink to="/audit" className={navLinkClass} onClick={onNavigate}>
                  <History size={18} className="shrink-0" />
                  Denetim Kayıtları
                </NavLink>
                <NavLink to="/kvkk-export" className={navLinkClass} onClick={onNavigate}>
                  <Database size={18} className="shrink-0" />
                  KVKK Veri Aktarma
                </NavLink>
                <NavLink to="/admin/system-health" className={navLinkClass} onClick={onNavigate}>
                  <Activity size={18} className="shrink-0" />
                  Sistem Sağlığı
                </NavLink>
                <NavLink to="/admin/event-audit" className={navLinkClass} onClick={onNavigate}>
                  <ListTree size={18} className="shrink-0" />
                  Olay Denetim Kaydı
                </NavLink>
              </>
            )}
          </>
        )}
      </nav>

      {/* User info at bottom — avatar + name + logout, calmer divider */}
      <div className="border-t border-white/6 px-4 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-honeywell-red/12 ring-1 ring-honeywell-red/20">
            <span className="text-[12px] font-semibold text-honeywell-red leading-none">
              {(user?.full_name || user?.email || '?').slice(0, 1).toUpperCase()}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-slate-100">
              {user?.full_name || t('common.user')}
            </p>
            <p className="truncate text-[11px] text-slate-500">{user?.email || ''}</p>
          </div>
          <button
            onClick={handleLogout}
            className="shrink-0 rounded-[10px] p-2 text-slate-400 hover:bg-white/4 hover:text-slate-100 transition-colors"
            aria-label={t('common.logout')}
            title={t('common.logout')}
          >
            <LogOut size={18} className="shrink-0" />
          </button>
        </div>
      </div>
    </aside>
  );
}
