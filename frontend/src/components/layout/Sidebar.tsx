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
  Briefcase,
  HandCoins,
  Wallet,
  Globe2,
  Trash2,
} from 'lucide-react';
import { approvalsApi } from '../../lib/api';
import type { TranslationKey } from '../../lib/i18n';

// Round-9 — sidebar groups are collapsible like the original "Yedek Parça"
// section. Per-section state is persisted in localStorage so user
// preferences survive reloads. The original single-key was kept around
// for backwards compatibility.
const COLLAPSE_STATE_KEY = 'sidebar-section-collapsed-v2';
const LEGACY_COLLAPSE_KEY = 'sidebar-yedek-parca-collapsed';

interface NavItem {
  label: TranslationKey | string;
  to: string;
  icon: ReactNode;
  roles?: string[];
  /** Optional badge renderer (e.g. pending approvals count). */
  badge?: number;
}

interface NavGroup {
  id: string;
  label: TranslationKey | string;
  icon: ReactNode;
  roles?: string[];
  items: NavItem[];
  /** Default collapsed state when nothing is in localStorage. */
  defaultCollapsed?: boolean;
}

function filterByRole<T extends { roles?: string[] }>(items: T[], role: string | undefined): T[] {
  if (!role) return items;
  return items.filter((item) => !item.roles || item.roles.includes(role));
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    'flex items-center gap-3 h-9 rounded-[10px] px-3 text-[13px] font-medium',
    'transition-[background-color,color] duration-150',
    isActive
      ? 'bg-honeywell-red/12 text-white ring-1 ring-honeywell-red/20'
      : 'text-slate-400 hover:bg-white/4 hover:text-slate-100',
  ].join(' ');
}

interface CollapsibleSectionProps {
  group: NavGroup;
  expanded: boolean;
  onToggle: () => void;
  onNavigate?: () => void;
  pendingApprovals?: number;
}

function CollapsibleSection({
  group,
  expanded,
  onToggle,
  onNavigate,
  pendingApprovals,
}: CollapsibleSectionProps) {
  const t = useT();
  const label =
    typeof group.label === 'string' && group.label.startsWith('nav.')
      ? t(group.label as TranslationKey)
      : (group.label as string);
  return (
    <div>
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between rounded-[10px] px-3 py-2 text-[13px] font-medium text-slate-300 hover:bg-white/4 hover:text-slate-100 transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-3">
          {group.icon}
          {label}
        </span>
        <ChevronRight
          size={14}
          className={`shrink-0 text-slate-500 transition-transform duration-150 ${
            expanded ? 'rotate-90' : ''
          }`}
        />
      </button>
      {expanded && (
        <div className="ml-3 mt-0.5 space-y-0.5 border-l border-white/6 pl-2">
          {group.items.map((item) => {
            const itemLabel =
              typeof item.label === 'string' && item.label.startsWith('nav.')
                ? t(item.label as TranslationKey)
                : (item.label as string);
            const showBadge = item.badge != null && item.badge > 0;
            const computedBadge =
              item.to === '/approvals' && pendingApprovals && pendingApprovals > 0
                ? pendingApprovals
                : showBadge
                  ? item.badge
                  : undefined;
            return (
              <NavLink key={item.to} to={item.to} className={navLinkClass} onClick={onNavigate}>
                {item.icon}
                <span className="flex-1 truncate">{itemLabel}</span>
                {computedBadge != null && (
                  <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-honeywell-red px-1.5 text-[10px] font-bold text-white">
                    {computedBadge}
                  </span>
                )}
              </NavLink>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const t = useT();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const userRole = user?.role;
  const canSeeSettings = !userRole || ['sales_manager', 'operations'].includes(userRole);
  const canSeeApprovals = userRole === 'sales_rep' || userRole === 'sales_manager';
  const canSeeAudit = userRole === 'sales_manager';

  // R14-FE-1 exempt: sidebar approval-count badge — empty badge is acceptable on transient failure
  const { data: pendingData } = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => approvalsApi.getPending(),
    enabled: canSeeApprovals,
    refetchInterval: 60_000,
  });
  const pendingCount = pendingData?.items?.length ?? 0;

  // ── Group definitions ───────────────────────────────────────────────
  const groups: NavGroup[] = [
    {
      id: 'sales',
      label: 'nav.section_sales',
      icon: <Radar size={18} className="shrink-0" />,
      roles: ['sales_rep', 'sales_manager'],
      items: [
        { label: 'nav.cockpit', to: '/cockpit', icon: <Radar size={16} className="shrink-0" /> },
        {
          label: 'nav.forecast',
          to: '/forecast',
          icon: <LineChart size={16} className="shrink-0" />,
          roles: ['sales_manager'],
        },
        {
          label: 'nav.network_intelligence',
          to: '/network-intelligence',
          icon: <NetworkIcon size={16} className="shrink-0" />,
          roles: ['sales_manager'],
        },
        { label: 'nav.board', to: '/board', icon: <Kanban size={16} className="shrink-0" /> },
        {
          label: 'nav.opportunities',
          to: '/opportunities',
          icon: <Layers size={16} className="shrink-0" />,
        },
        {
          label: 'nav.planning_studio',
          to: '/planning-studio',
          icon: <ListFilter size={16} className="shrink-0" />,
        },
        {
          label: 'nav.sales_analytics',
          to: '/sales-analytics',
          icon: <TrendingUp size={16} className="shrink-0" />,
          roles: ['sales_manager'],
        },
        {
          label: 'nav.at_risk',
          to: '/at-risk',
          icon: <AlertTriangle size={16} className="shrink-0" />,
        },
      ],
    },
    {
      id: 'customers',
      label: 'nav.section_customers',
      icon: <Users size={18} className="shrink-0" />,
      roles: ['sales_rep', 'sales_manager'],
      items: [
        {
          label: 'nav.customers',
          to: '/customers',
          icon: <Users size={16} className="shrink-0" />,
        },
        {
          label: 'nav.high_intent',
          to: '/customers/high-intent',
          icon: <Target size={16} className="shrink-0" />,
        },
        { label: 'nav.leads', to: '/leads', icon: <Target size={16} className="shrink-0" /> },
      ],
    },
    {
      id: 'spare_parts',
      label: 'nav.spare_parts',
      icon: <Wrench size={18} className="shrink-0" />,
      items: [
        {
          label: 'nav.emails',
          to: '/emails',
          icon: <Mail size={16} className="shrink-0" />,
          roles: ['sales_rep', 'sales_manager'],
        },
        { label: 'nav.parts', to: '/parts', icon: <Cog size={16} className="shrink-0" /> },
        {
          label: 'nav.parts_intel',
          to: '/parts-intel',
          icon: <Cog size={16} className="shrink-0" />,
          roles: ['sales_manager', 'operations'],
        },
        {
          label: 'nav.quotes',
          to: '/quotes',
          icon: <FileText size={16} className="shrink-0" />,
          roles: ['sales_rep', 'sales_manager'],
        },
      ],
    },
    {
      id: 'revenue',
      label: 'nav.section_revenue',
      icon: <Wallet size={18} className="shrink-0" />,
      roles: ['sales_rep', 'sales_manager'],
      items: [
        {
          label: 'nav.subscriptions',
          to: '/subscriptions',
          icon: <RefreshCw size={16} className="shrink-0" />,
        },
        {
          label: 'nav.contracts',
          to: '/contracts',
          icon: <FileCheck size={16} className="shrink-0" />,
        },
        {
          label: 'nav.invoices',
          to: '/invoices',
          icon: <ReceiptText size={16} className="shrink-0" />,
        },
        {
          label: 'nav.revenue_recognition',
          to: '/revenue-recognition',
          icon: <TrendingUp size={16} className="shrink-0" />,
        },
        {
          label: 'nav.campaigns',
          to: '/campaigns',
          icon: <Megaphone size={16} className="shrink-0" />,
        },
      ],
    },
    {
      id: 'approvals',
      label: 'nav.section_approvals',
      icon: <ClipboardCheck size={18} className="shrink-0" />,
      roles: ['sales_rep', 'sales_manager'],
      items: [
        {
          label: 'nav.leaderboard',
          to: '/leaderboard',
          icon: <Trophy size={16} className="shrink-0" />,
        },
        {
          label: 'nav.approvals',
          to: '/approvals',
          icon: <ClipboardCheck size={16} className="shrink-0" />,
        },
        {
          label: 'nav.approval_rules',
          to: '/approvals/rules',
          icon: <Workflow size={16} className="shrink-0" />,
          roles: ['sales_manager'],
        },
      ],
    },
    {
      id: 'tools',
      label: 'nav.section_tools',
      icon: <Brain size={18} className="shrink-0" />,
      roles: ['sales_rep', 'sales_manager'],
      items: [
        {
          label: 'nav.ai_assistant',
          to: '/ai/insights',
          icon: <Brain size={16} className="shrink-0" />,
        },
        {
          label: 'nav.ai_tasks',
          to: '/ai/tasks',
          icon: <ListChecks size={16} className="shrink-0" />,
        },
        {
          label: 'nav.insights',
          to: '/insights',
          icon: <TrendingUp size={16} className="shrink-0" />,
        },
        {
          label: 'nav.report_builder',
          to: '/reports/builder',
          icon: <BarChart3 size={16} className="shrink-0" />,
          roles: ['sales_manager'],
        },
        {
          label: 'nav.email_templates',
          to: '/email-templates',
          icon: <FilePenLine size={16} className="shrink-0" />,
        },
        {
          label: 'nav.dashboards',
          to: '/dashboards',
          icon: <LayoutGrid size={16} className="shrink-0" />,
        },
      ],
    },
    {
      id: 'playbooks',
      label: 'nav.section_playbooks',
      icon: <BookOpen size={18} className="shrink-0" />,
      roles: ['sales_manager'],
      items: [
        {
          label: 'nav.playbooks',
          to: '/playbooks',
          icon: <BookOpen size={16} className="shrink-0" />,
        },
        {
          label: 'nav.playbook_templates',
          to: '/playbooks/templates',
          icon: <FileText size={16} className="shrink-0" />,
        },
        {
          label: 'nav.playbook_analytics',
          to: '/playbooks/analytics',
          icon: <BarChart2 size={16} className="shrink-0" />,
        },
        {
          label: 'nav.coaching',
          to: '/coaching',
          icon: <GraduationCap size={16} className="shrink-0" />,
        },
      ],
    },
    {
      id: 'engagement',
      label: 'nav.section_engagement',
      icon: <MessageSquare size={18} className="shrink-0" />,
      roles: ['sales_rep', 'sales_manager'],
      items: [
        {
          label: 'nav.transcripts',
          to: '/engagement/transcripts',
          icon: <MessageSquare size={16} className="shrink-0" />,
        },
        {
          label: 'nav.keywords',
          to: '/engagement/keywords',
          icon: <Tag size={16} className="shrink-0" />,
        },
        {
          label: 'nav.sequences',
          to: '/engagement/sequences',
          icon: <ListChecks size={16} className="shrink-0" />,
        },
        {
          label: 'nav.segments',
          to: '/engagement/segments',
          icon: <UsersRound size={16} className="shrink-0" />,
        },
        {
          label: 'nav.scorecards',
          to: '/engagement/scorecards',
          icon: <Trophy size={16} className="shrink-0" />,
        },
      ],
    },
    {
      id: 'compliance',
      label: 'nav.section_compliance',
      icon: <Shield size={18} className="shrink-0" />,
      roles: ['sales_manager', 'operations'],
      items: [
        {
          label: 'nav.compliance',
          to: '/compliance',
          icon: <Shield size={16} className="shrink-0" />,
        },
        {
          label: 'nav.retention',
          to: '/compliance/retention',
          icon: <Database size={16} className="shrink-0" />,
        },
        {
          label: 'nav.breaches',
          to: '/compliance/breaches',
          icon: <AlertTriangle size={16} className="shrink-0" />,
        },
      ],
    },
    {
      id: 'admin',
      label: 'nav.section_admin',
      icon: <Briefcase size={18} className="shrink-0" />,
      roles: ['sales_manager'],
      items: [
        {
          label: 'nav.custom_fields',
          to: '/admin/custom-fields',
          icon: <FormInput size={16} className="shrink-0" />,
        },
        {
          label: 'nav.ai_attributes',
          to: '/admin/ai-attributes',
          icon: <Sparkles size={16} className="shrink-0" />,
        },
        {
          label: 'nav.field_permissions',
          to: '/admin/field-permissions',
          icon: <KeyRound size={16} className="shrink-0" />,
        },
        {
          label: 'nav.product_rules',
          to: '/admin/product-rules',
          icon: <Scale size={16} className="shrink-0" />,
        },
        {
          label: 'nav.workflow_rules',
          to: '/admin/workflow-rules',
          icon: <Workflow size={16} className="shrink-0" />,
        },
        {
          label: 'nav.data_quality',
          to: '/admin/data-quality',
          icon: <BarChart2 size={16} className="shrink-0" />,
        },
        {
          label: 'nav.trash',
          to: '/admin/trash',
          icon: <Trash2 size={16} className="shrink-0" />,
        },
        {
          label: 'nav.territories',
          to: '/admin/territories',
          icon: <Map size={16} className="shrink-0" />,
        },
        {
          label: 'nav.pricing_admin',
          to: '/admin/pricing',
          icon: <HandCoins size={16} className="shrink-0" />,
        },
        {
          label: 'nav.live_chat',
          to: '/admin/chat',
          icon: <MessageSquare size={16} className="shrink-0" />,
        },
        {
          label: 'nav.user_management',
          to: '/users',
          icon: <UsersRound size={16} className="shrink-0" />,
        },
        {
          label: 'nav.reports_legacy',
          to: '/reports',
          icon: <FileText size={16} className="shrink-0" />,
        },
        {
          label: 'nav.integrations',
          to: '/integrations',
          icon: <Plug size={16} className="shrink-0" />,
        },
      ],
      defaultCollapsed: true,
    },
    {
      id: 'audit',
      label: 'nav.section_audit',
      icon: <History size={18} className="shrink-0" />,
      roles: ['sales_manager'],
      items: [
        { label: 'nav.audit_log', to: '/audit', icon: <History size={16} className="shrink-0" /> },
        {
          label: 'nav.kvkk_export',
          to: '/kvkk-export',
          icon: <Database size={16} className="shrink-0" />,
        },
        {
          label: 'nav.system_health',
          to: '/admin/system-health',
          icon: <Activity size={16} className="shrink-0" />,
        },
        {
          label: 'nav.event_audit',
          to: '/admin/event-audit',
          icon: <ListTree size={16} className="shrink-0" />,
        },
      ],
      defaultCollapsed: true,
    },
  ];

  // Filter groups + their items by role.
  const visibleGroups = filterByRole(groups, userRole)
    .map((g) => ({ ...g, items: filterByRole(g.items, userRole) }))
    .filter((g) => g.items.length > 0);

  // Per-section expand state.
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const saved = localStorage.getItem(COLLAPSE_STATE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved) as Record<string, boolean>;
      } catch {
        /* fall through */
      }
    }
    // First load: legacy single-key was for spare_parts only.
    const legacy = localStorage.getItem(LEGACY_COLLAPSE_KEY);
    const legacyCollapsed = legacy ? JSON.parse(legacy) === true : false;
    return groups.reduce<Record<string, boolean>>((acc, g) => {
      if (g.id === 'spare_parts') {
        acc[g.id] = !legacyCollapsed;
      } else {
        acc[g.id] = !g.defaultCollapsed;
      }
      return acc;
    }, {});
  });

  useEffect(() => {
    localStorage.setItem(COLLAPSE_STATE_KEY, JSON.stringify(expanded));
  }, [expanded]);

  // Auto-expand the section that contains the active route.
  useEffect(() => {
    for (const g of visibleGroups) {
      const hit = g.items.some((item) => location.pathname.startsWith(item.to));
      if (hit && !expanded[g.id]) {
        setExpanded((prev) => ({ ...prev, [g.id]: true }));
        break;
      }
    }
    // visibleGroups is recomputed each render but its identity is stable
    // enough for effect dep purposes; we deliberately omit it here to
    // avoid an infinite render loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const toggleSection = (id: string) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <aside className="flex h-screen w-[260px] flex-col bg-slate-950 border-r border-white/6">
      {/* Brand block */}
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
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {/* Top-level Anasayfa link — the only flat entry */}
        <NavLink to="/" end className={navLinkClass} onClick={onNavigate}>
          <LayoutDashboard size={18} className="shrink-0" />
          {t('nav.home')}
        </NavLink>

        <div className="pt-3 space-y-0.5">
          {visibleGroups.map((g) => (
            <CollapsibleSection
              key={g.id}
              group={g}
              expanded={expanded[g.id] ?? !g.defaultCollapsed}
              onToggle={() => toggleSection(g.id)}
              onNavigate={onNavigate}
              pendingApprovals={pendingCount}
            />
          ))}
        </div>

        {/* Settings always available at the bottom of nav, kept flat */}
        {canSeeSettings && (
          <div className="pt-3 space-y-0.5">
            <NavLink to="/settings" className={navLinkClass} onClick={onNavigate}>
              <Settings size={18} className="shrink-0" />
              {t('nav.settings')}
            </NavLink>
            <NavLink to="/settings/pipelines" className={navLinkClass} onClick={onNavigate}>
              <GitBranch size={18} className="shrink-0" />
              {t('nav.pipeline_settings')}
            </NavLink>
            {userRole === 'sales_manager' && (
              <NavLink to="/reports/saved" className={navLinkClass} onClick={onNavigate}>
                <BarChart3 size={18} className="shrink-0" />
                {t('nav.reports')}
              </NavLink>
            )}
          </div>
        )}

        {/* Suppress unused-import warnings for legacy locals (kept for
            potential ad-hoc top-level entries before next cleanup). */}
        {false && (
          <span className="hidden">
            {canSeeAudit ? '' : ''}
            <Globe2 size={1} />
          </span>
        )}
      </nav>

      {/* User info at bottom */}
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
