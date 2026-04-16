import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts';
import {
  AlertTriangle,
  TrendingUp,
  Clock,
  Bot,
  Activity,
  CheckCircle2,
  Play,
  XCircle,
  Swords,
  ShieldAlert,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import {
  cockpitApi,
  playbookApi,
  coachingApi,
  aiApi,
  dealHealthApi,
  analyticsApi,
} from '../../lib/api';
import { formatCurrency, formatDate, formatDateTime } from '../../lib/formatters';
import { useAuthStore } from '../../stores/authStore';

import type {
  CockpitKpis,
  RevenueSignalItem,
  CockpitAction,
  CoachingOverview,
  ActivityDroughtItem,
  RevenueLeakResult,
  RevenueLeakItem,
} from '../../lib/types';

// ── Severity / priority color helpers ────────────────

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'default';

const SEVERITY_VARIANT: Record<string, BadgeVariant> = {
  critical: 'danger',
  high: 'warning',
  medium: 'warning',
  low: 'default',
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'Kritik',
  high: 'Yuksek',
  medium: 'Orta',
  low: 'Dusuk',
};

const PRIORITY_VARIANT: Record<string, BadgeVariant> = {
  urgent: 'danger',
  high: 'warning',
  normal: 'info',
  low: 'default',
};

const PRIORITY_LABEL: Record<string, string> = {
  urgent: 'Acil',
  high: 'Yuksek',
  normal: 'Normal',
  low: 'Dusuk',
};

// ── KPI Strip ────────────────────────────────────────

function KpiStrip({ data, isLoading }: { data?: CockpitKpis; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    );
  }

  if (!data) return null;

  const kpis = [
    {
      label: 'Pipeline',
      value: formatCurrency(data.pipeline_total, data.pipeline_currency),
      icon: <TrendingUp size={18} className="text-blue-500" />,
    },
    {
      label: 'Kazanma Orani',
      value: `%${(data.win_rate * 100).toFixed(1)}`,
      icon: <CheckCircle2 size={18} className="text-green-500" />,
    },
    {
      label: 'Risk Altinda',
      value: String(data.at_risk_count),
      icon: <AlertTriangle size={18} className="text-red-500" />,
    },
    {
      label: 'Ort. Hiz (gun)',
      value: String(data.avg_deal_velocity_days),
      icon: <Clock size={18} className="text-amber-500" />,
    },
    {
      label: 'AI Gorevler',
      value: String(data.open_ai_tasks),
      icon: <Bot size={18} className="text-purple-500" />,
    },
    {
      label: 'Sinyaller',
      value: String(data.signal_stats.total),
      icon: <Activity size={18} className="text-indigo-500" />,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi) => (
        <div key={kpi.label} className="card-modern flex flex-col gap-2 px-5 py-4">
          <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            {kpi.icon}
            {kpi.label}
          </div>
          <span className="text-xl font-bold text-gray-900 dark:text-white">{kpi.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Signal Stream ────────────────────────────────────

function SignalStream() {
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'signals', severityFilter],
    queryFn: () =>
      cockpitApi.getSignals(severityFilter !== 'all' ? { severity: severityFilter } : undefined),
    refetchInterval: 30_000,
  });

  const resolveMutation = useMutation({
    mutationFn: cockpitApi.resolveSignal,
    onSuccess: () => {
      toast.success('Sinyal cozumlendi');
      queryClient.invalidateQueries({ queryKey: ['cockpit'] });
    },
  });

  const signals: RevenueSignalItem[] = data?.items ?? [];

  return (
    <Card
      title="Sinyal Akisi"
      action={
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        >
          <option value="all">Tumu</option>
          <option value="critical">Kritik</option>
          <option value="high">Yuksek</option>
          <option value="medium">Orta</option>
          <option value="low">Dusuk</option>
        </select>
      }
    >
      {isLoading ? (
        <Skeleton variant="line" count={5} />
      ) : signals.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">Sinyal bulunamadi</p>
      ) : (
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          {signals.map((signal) => (
            <div
              key={signal.id}
              className="flex items-start justify-between gap-3 rounded-lg border border-gray-100 p-3 dark:border-gray-700"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge variant={SEVERITY_VARIANT[signal.severity] ?? 'default'} size="sm">
                    {SEVERITY_LABEL[signal.severity] ?? signal.severity}
                  </Badge>
                  <span className="text-xs text-gray-400">{signal.signal_type}</span>
                </div>
                {signal.recommended_action && (
                  <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                    {signal.recommended_action}
                  </p>
                )}
                <p className="mt-1 text-xs text-gray-400">{formatDateTime(signal.created_at)}</p>
              </div>
              {!signal.is_resolved && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => resolveMutation.mutate(signal.id)}
                  loading={resolveMutation.isPending}
                  title="Cozumle"
                >
                  <CheckCircle2 size={16} />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Action Queue ─────────────────────────────────────

function ActionQueue() {
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'actions'],
    queryFn: cockpitApi.getActions,
    refetchInterval: 60_000,
  });

  const actions: CockpitAction[] = data?.items ?? [];

  return (
    <Card title="AI Onerilen Gorevler">
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : actions.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">Bekleyen gorev yok</p>
      ) : (
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          {actions.map((action) => (
            <div
              key={action.id}
              className="rounded-lg border border-gray-100 p-3 dark:border-gray-700"
            >
              <div className="flex items-center gap-2">
                <Badge variant={PRIORITY_VARIANT[action.priority] ?? 'default'} size="sm">
                  {PRIORITY_LABEL[action.priority] ?? action.priority}
                </Badge>
              </div>
              <p className="mt-1 text-sm font-medium text-gray-800 dark:text-gray-200">
                {action.title}
              </p>
              {action.description && (
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {action.description}
                </p>
              )}
              {action.due_at && (
                <p className="mt-1 text-xs text-gray-400">Son tarih: {formatDate(action.due_at)}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Trend Charts ─────────────────────────────────────

function TrendCharts() {
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'trends'],
    queryFn: cockpitApi.getTrends,
  });

  const chartData: { week: string; signal_count: number }[] = data?.signal_volume ?? [];

  return (
    <Card title="Sinyal Hacmi Trendi">
      {isLoading ? (
        <Skeleton className="h-64 rounded-xl" />
      ) : chartData.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">Trend verisi yok</p>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="week" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                fontSize: 13,
                border: '1px solid #e5e7eb',
              }}
            />
            <Bar dataKey="signal_count" name="Sinyal Sayisi" fill="#ef4444" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

// ── Playbook Panel ───────────────────────────────────

interface PlaybookExecution {
  id: number;
  playbook_name: string;
  status: string;
  started_at: string;
  opportunity_id: number | null;
}

function PlaybookPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['playbook', 'executions'],
    queryFn: () => playbookApi.getExecutions({ status: 'running' }),
    refetchInterval: 60_000,
  });

  const cancelMutation = useMutation({
    mutationFn: playbookApi.cancelExecution,
    onSuccess: () => {
      toast.success('Playbook iptal edildi');
      queryClient.invalidateQueries({ queryKey: ['playbook'] });
    },
  });

  const executions: PlaybookExecution[] = data?.items ?? data ?? [];

  return (
    <Card title="Aktif Playbook Calismalari">
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : executions.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">Aktif calisma yok</p>
      ) : (
        <div className="space-y-2">
          {executions.map((exec) => (
            <div
              key={exec.id}
              className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3 dark:border-gray-700"
            >
              <div className="flex items-center gap-3">
                <Play size={16} className="text-green-500" />
                <div>
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {exec.playbook_name}
                  </p>
                  <p className="text-xs text-gray-400">{formatDateTime(exec.started_at)}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => cancelMutation.mutate(exec.id)}
                loading={cancelMutation.isPending}
                title="Iptal Et"
              >
                <XCircle size={16} className="text-red-400" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Coaching Panel (manager only) ────────────────────

function CoachingPanel() {
  const { data, isLoading } = useQuery<CoachingOverview>({
    queryKey: ['coaching', 'overview'],
    queryFn: coachingApi.getOverview,
    refetchInterval: 120_000,
  });

  const riskVariant = (level: string): BadgeVariant => {
    if (level === 'high' || level === 'critical') return 'danger';
    if (level === 'medium') return 'warning';
    return 'success';
  };

  return (
    <Card title="Temsilci Koocluk Skorlari">
      {isLoading ? (
        <Skeleton variant="table" />
      ) : !data || data.reps.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">Veri bulunamadi</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">Temsilci</th>
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">Skor</th>
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">Risk</th>
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">Oneriler</th>
              </tr>
            </thead>
            <tbody>
              {data.reps.map((rep) => (
                <tr
                  key={rep.user_id}
                  className="border-b border-gray-100 last:border-0 dark:border-gray-700"
                >
                  <td className="py-2 font-medium text-gray-800 dark:text-gray-200">
                    {rep.user_name}
                  </td>
                  <td className="py-2 text-gray-700 dark:text-gray-300">{rep.score.toFixed(0)}</td>
                  <td className="py-2">
                    <Badge variant={riskVariant(rep.risk_level)} size="sm">
                      {rep.risk_level}
                    </Badge>
                  </td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">
                    {rep.recommendations.slice(0, 2).join('; ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ── Competitive Intel Panel ─────────────────────────

function CompetitiveIntelPanel() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['ai-competitive-intel'],
    queryFn: () => aiApi.competitiveIntel(90),
    retry: false,
  });

  const crawlMutation = useMutation({
    mutationFn: aiApi.crawlCompetitors,
    onSuccess: () => {
      toast.success('Rakip tarama tamamlandi');
      queryClient.invalidateQueries({ queryKey: ['ai-competitive-intel'] });
    },
    onError: () => {
      toast.error('Rakip tarama basarisiz oldu');
    },
  });

  const competitors = data?.competitors ?? data?.by_competitor ?? [];

  return (
    <Card
      title="Rekabet Istihbarati"
      action={
        <Button
          variant="secondary"
          size="sm"
          onClick={() => crawlMutation.mutate()}
          loading={crawlMutation.isPending}
        >
          Rakip Tara
        </Button>
      }
    >
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : competitors.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">
          Son 90 gunde rakip bahsi bulunamadi
        </p>
      ) : (
        <div className="space-y-3">
          {competitors
            .slice(0, 5)
            .map(
              (comp: {
                name?: string;
                competitor?: string;
                mention_count: number;
                sentiment_avg?: number;
                recent_mentions?: { source_type: string; context_snippet: string }[];
              }) => {
                const compName = comp.name ?? comp.competitor ?? 'Bilinmiyor';
                return (
                  <div
                    key={compName}
                    className="rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Swords size={14} className="text-red-400" />
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">
                          {compName}
                        </span>
                      </div>
                      <Badge variant={comp.mention_count > 5 ? 'danger' : 'info'} size="sm">
                        {comp.mention_count} bahsetme
                      </Badge>
                    </div>
                    {comp.sentiment_avg != null && (
                      <p className="text-xs text-gray-500 mb-1">
                        Duygu:{' '}
                        {comp.sentiment_avg > 0
                          ? 'Pozitif'
                          : comp.sentiment_avg < 0
                            ? 'Negatif'
                            : 'Notr'}
                      </p>
                    )}
                    {comp.recent_mentions?.slice(0, 1).map((m, i) => (
                      <p key={i} className="text-xs text-gray-400 truncate">
                        [{m.source_type}] {m.context_snippet}
                      </p>
                    ))}
                  </div>
                );
              },
            )}
        </div>
      )}
    </Card>
  );
}

// ── At-Risk Deals Panel ─────────────────────────────

function AtRiskDealsPanel() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['deal-health-at-risk-cockpit'],
    queryFn: () => dealHealthApi.getAtRisk(40),
    refetchInterval: 120_000,
  });

  const deals = data?.opportunities ?? data?.deals ?? data?.items ?? [];

  return (
    <Card title="Riskli Firsatlar">
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : deals.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">Risk altinda firsat yok</p>
      ) : (
        <div className="space-y-2">
          {deals
            .slice(0, 5)
            .map(
              (deal: {
                opportunity_id: number;
                title: string;
                score: number;
                risk_level: string;
              }) => (
                <button
                  key={deal.opportunity_id}
                  type="button"
                  onClick={() => navigate(`/opportunities/${deal.opportunity_id}`)}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <ShieldAlert
                      size={14}
                      className={deal.score < 30 ? 'text-red-500' : 'text-amber-500'}
                    />
                    <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {deal.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-bold ${deal.score < 30 ? 'text-red-600' : 'text-amber-600'}`}
                    >
                      {deal.score}
                    </span>
                    <Badge
                      variant={deal.risk_level === 'critical' ? 'danger' : 'warning'}
                      size="sm"
                    >
                      {deal.risk_level === 'critical' ? 'Kritik' : 'Risk'}
                    </Badge>
                  </div>
                </button>
              ),
            )}
        </div>
      )}
    </Card>
  );
}

// ── Activity Drought Panel (Modul 6) ──────────────────

function ActivityDroughtPanel() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['activity-drought'],
    queryFn: () => analyticsApi.getActivityDrought(7),
    refetchInterval: 120_000,
  });

  const items: ActivityDroughtItem[] = data?.items ?? [];

  const STAGE_LABELS: Record<string, string> = {
    prospecting: 'Arastirma',
    qualified: 'Nitelenmis',
    proposal: 'Teklif',
    negotiation: 'Muzakere',
  };

  return (
    <Card title="Aktivite Kurugu">
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">Son 7 gunde aktivitesiz firsat yok</p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 7).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => navigate(`/opportunities/${item.id}`)}
              className="flex w-full items-center justify-between rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Clock
                  size={14}
                  className={item.days_since_last > 14 ? 'text-red-500' : 'text-amber-500'}
                />
                <div className="min-w-0 text-left">
                  <span className="text-sm font-medium text-gray-900 dark:text-white truncate block">
                    {item.title}
                  </span>
                  <span className="text-xs text-gray-400">
                    {item.owner_name} - {STAGE_LABELS[item.stage] || item.stage}
                  </span>
                </div>
              </div>
              <Badge variant={item.days_since_last > 14 ? 'danger' : 'warning'} size="sm">
                {item.days_since_last} gun
              </Badge>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Revenue Leak Panel (Modul 10) ───────────────────

function RevenueLeakPanel() {
  const navigate = useNavigate();
  const { data: leaksRaw, isLoading } = useQuery({
    queryKey: ['revenue-leaks-cockpit'],
    queryFn: () => analyticsApi.getRevenueLeaks(),
    refetchInterval: 120_000,
  });

  const leaks: RevenueLeakResult | undefined = leaksRaw?.data;

  const STAGE_LABELS: Record<string, string> = {
    prospecting: 'Arastirma',
    qualified: 'Nitelenmis',
    proposal: 'Teklif',
    negotiation: 'Muzakere',
  };

  return (
    <Card title="Gelir Sizintisi">
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : !leaks || leaks.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">Sizinti tespit edilmedi</p>
      ) : (
        <div>
          <div className="mb-3 flex items-center gap-3">
            <span className="text-2xl font-bold text-red-600">
              {formatCurrency(leaks.total_leak_amount, 'TRY')}
            </span>
            <Badge variant="danger">{leaks.total_leaks} firsat</Badge>
          </div>
          <div className="space-y-2">
            {leaks.items.slice(0, 5).map((item: RevenueLeakItem) => (
              <button
                key={item.opportunity_id}
                type="button"
                onClick={() => navigate(`/opportunities/${item.opportunity_id}`)}
                className="flex w-full items-start justify-between rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="min-w-0 flex-1 text-left">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {item.title}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {item.owner_name} - {STAGE_LABELS[item.stage] || item.stage}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.factors.map((f) => (
                      <Badge key={f.name} variant="warning" size="sm">
                        {f.label}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="ml-3 flex flex-col items-end gap-1">
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {formatCurrency(item.amount, 'TRY')}
                  </span>
                  <span
                    className={`text-sm font-bold ${item.leak_score >= 50 ? 'text-red-600' : 'text-amber-600'}`}
                  >
                    {item.leak_score}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Main Page ────────────────────────────────────────

// ── Work Hub Tabs ──────────────────────────────────

const WORK_HUB_TABS = [
  { key: 'sequences', label: 'Diziler', icon: Play },
  { key: 'feed', label: 'Sinyal Akisi', icon: Activity },
  { key: 'todo', label: 'Gorevler', icon: CheckCircle2 },
] as const;

type WorkHubTab = (typeof WORK_HUB_TABS)[number]['key'];

function SequencesTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'sequence-analytics'],
    queryFn: async () => {
      const { sequenceV2Api } = await import('../../lib/api');
      return sequenceV2Api.getAnalytics();
    },
    refetchInterval: 120_000,
  });

  const { data: enrollments } = useQuery({
    queryKey: ['sequences', 'enrollments'],
    queryFn: async () => {
      const { engagementApi } = await import('../../lib/api');
      return engagementApi.listEnrollments();
    },
    refetchInterval: 60_000,
  });

  if (isLoading) return <Skeleton className="h-48 rounded-xl" />;

  const analytics = data || {};
  const activeEnrollments = (enrollments?.enrollments || []).filter(
    (e: Record<string, unknown>) => e.status === 'active',
  );

  return (
    <div className="space-y-4">
      {/* Analytics KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border p-3">
          <div className="text-xs text-gray-500">Ort. Temas/Hedef</div>
          <div className="text-xl font-semibold">{analytics.avg_touches_per_target ?? '-'}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-xs text-gray-500">Toplam Step Run</div>
          <div className="text-xl font-semibold">{analytics.total_step_runs ?? 0}</div>
        </div>
        {Object.entries(analytics.status_distribution || {}).map(([status, count]) => (
          <div key={status} className="rounded-lg border p-3">
            <div className="text-xs text-gray-500 capitalize">{status}</div>
            <div className="text-xl font-semibold">{count as number}</div>
          </div>
        ))}
      </div>

      {/* Exit Reason Distribution */}
      {analytics.exit_reason_distribution && Object.keys(analytics.exit_reason_distribution).length > 0 && (
        <Card title="Tamamlama Nedeni Dagilimi">
          <div className="flex flex-wrap gap-2">
            {Object.entries(analytics.exit_reason_distribution).map(([reason, count]) => (
              <Badge key={reason} variant="default">
                {reason}: {count as number}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Active Enrollments (next actions) */}
      <Card title={`Aktif Diziler (${activeEnrollments.length})`}>
        {activeEnrollments.length === 0 ? (
          <p className="text-sm text-gray-400">Aktif dizi kaydi yok</p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {activeEnrollments.slice(0, 15).map((e: Record<string, unknown>) => (
              <div
                key={e.id as number}
                className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium">Enrollment #{e.id as number}</span>
                  <span className="text-gray-500 ml-2">Adim {e.current_step as number}</span>
                </div>
                <Badge variant={e.is_paused ? 'warning' : 'info'}>
                  {e.is_paused ? 'Duraklatildi' : 'Aktif'}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default function CockpitPage() {
  const user = useAuthStore((state) => state.user);
  const isManager = user?.role === 'sales_manager';
  const [activeTab, setActiveTab] = useState<WorkHubTab>('feed');

  const { data: kpis, isLoading: isKpisLoading } = useQuery<CockpitKpis>({
    queryKey: ['cockpit', 'kpis'],
    queryFn: cockpitApi.getKpis,
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Gelir Kokpiti"
        description="Pipeline, sinyaller ve AI destekli gorev yonetimi"
      />

      {/* KPI Strip */}
      <KpiStrip data={kpis} isLoading={isKpisLoading} />

      {/* Work Hub — 3 Tab Layout */}
      <div>
        <div className="flex border-b mb-4">
          {WORK_HUB_TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
                  activeTab === tab.key
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {activeTab === 'sequences' && <SequencesTab />}
        {activeTab === 'feed' && (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <SignalStream />
            </div>
            <div>
              <TrendCharts />
            </div>
          </div>
        )}
        {activeTab === 'todo' && <ActionQueue />}
      </div>

      {/* Competitive Intel + At-Risk Deals */}
      <div className="grid gap-6 lg:grid-cols-2">
        <CompetitiveIntelPanel />
        <AtRiskDealsPanel />
      </div>

      {/* Revenue Leak Panel (Modul 10) */}
      <RevenueLeakPanel />

      {/* Activity Drought Panel */}
      <ActivityDroughtPanel />

      {/* Playbook Panel */}
      <PlaybookPanel />

      {/* Coaching Panel (manager only) */}
      {isManager && <CoachingPanel />}
    </div>
  );
}
