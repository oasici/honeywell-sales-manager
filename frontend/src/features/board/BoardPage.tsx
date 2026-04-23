import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Target } from 'lucide-react';
import { boardApi, customersApi, dealHealthApi, pipelinesApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { DealHealthBadge } from './DealHealthBadge';
import { formatCurrency } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import type {
  KanbanColumn,
  BoardSummary,
  Customer,
  Opportunity,
  DealHealthReport,
  Pipeline,
  HighIntentListResponse,
} from '../../lib/types';

const STAGE_LABELS: Record<string, string> = {
  prospecting: 'Arastirma',
  qualified: 'Nitelenmis',
  proposal: 'Teklif',
  negotiation: 'Muzakere',
  closed_won: 'Kazanildi',
  closed_lost: 'Kaybedildi',
};

const STAGE_COLORS: Record<string, string> = {
  prospecting: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  qualified: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  proposal: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  negotiation: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  closed_won: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  closed_lost: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

interface KanbanCardProps {
  opp: Opportunity;
  healthScore?: { score: number; risk_level: string } | null;
}

function KanbanCard({ opp, healthScore }: KanbanCardProps) {
  const navigate = useNavigate();
  const t = useT();
  const lastActivityDays = useMemo(() => {
    if (!opp.last_activity_at) return null;
    const dt = new Date(opp.last_activity_at);
    if (Number.isNaN(dt.getTime())) return null;
    const diffMs = Date.now() - dt.getTime();
    return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
  }, [opp.last_activity_at]);

  return (
    <button
      type="button"
      onClick={() => navigate(`/opportunities/${opp.id}`)}
      className="w-full rounded-lg border border-gray-200 bg-white p-3 text-left shadow-sm hover:shadow-md transition-shadow dark:border-gray-700 dark:bg-gray-800"
    >
      <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{opp.title}</p>
      {opp.customer && (
        <p className="mt-0.5 text-xs font-medium text-gray-600 dark:text-gray-300 truncate">
          {opp.customer.name}
        </p>
      )}
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {opp.amount != null ? (
            <span className="text-sm font-bold text-gray-800 dark:text-gray-200">
              {formatCurrency(opp.amount, opp.currency)}
            </span>
          ) : (
            <span className="text-xs text-gray-400">-</span>
          )}
          {healthScore && (
            <DealHealthBadge score={healthScore.score} riskLevel={healthScore.risk_level} />
          )}
        </div>
        {opp.rotting_days > 7 && (
          <span
            title={t('board.rotting_tooltip')}
            className="text-[10px] font-medium text-red-600 dark:text-red-400"
          >
            {opp.rotting_days}g
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {typeof opp.open_tasks_count === 'number' && opp.open_tasks_count > 0 && (
            <span className="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-bold text-violet-800 dark:bg-violet-900/30 dark:text-violet-200">
              {opp.open_tasks_count} task
            </span>
          )}
          {typeof lastActivityDays === 'number' && (
            <span
              title={t('board.rotting_tooltip')}
              className="text-[10px] font-medium text-gray-500 dark:text-gray-400"
            >
              {t('board.last_activity_fmt').replace('{{d}}', String(lastActivityDays))}
            </span>
          )}
        </div>
        {opp.owner && <p className="text-[10px] text-gray-400 truncate">{opp.owner.full_name}</p>}
      </div>
    </button>
  );
}

export default function BoardPage() {
  const t = useT();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [selectedPipelineId, setSelectedPipelineId] = useState<number | null>(null);
  const [minRottingDays, setMinRottingDays] = useState<number>(0);
  const [minOpenTasks, setMinOpenTasks] = useState<number>(0);
  const [customerId, setCustomerId] = useState<number | ''>('');
  const [customerQuery, setCustomerQuery] = useState('');
  const [debouncedCustomerQuery, setDebouncedCustomerQuery] = useState('');
  const [dealHealthRisk, setDealHealthRisk] = useState<string>('');

  useEffect(() => {
    const mrd = searchParams.get('min_rotting_days');
    if (mrd != null && mrd !== '') {
      const n = parseInt(mrd, 10);
      if (!Number.isNaN(n) && n >= 0) setMinRottingDays(n);
    }
    const mot = searchParams.get('min_open_tasks');
    if (mot != null && mot !== '') {
      const n = parseInt(mot, 10);
      if (!Number.isNaN(n) && n >= 0) setMinOpenTasks(n);
    }
    const cid = searchParams.get('customer_id');
    if (cid != null && cid !== '') {
      const n = parseInt(cid, 10);
      if (!Number.isNaN(n) && n > 0) setCustomerId(n);
    }
    const dhr = searchParams.get('deal_health_risk');
    if (dhr === 'critical' || dhr === 'high_risk' || dhr === 'at_risk' || dhr === 'healthy') {
      setDealHealthRisk(dhr);
    }
  }, [searchParams]);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedCustomerQuery(customerQuery.trim()), 300);
    return () => window.clearTimeout(t);
  }, [customerQuery]);

  const { data: pipelines = [] } = useQuery<Pipeline[]>({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await pipelinesApi.list();
      return res?.pipelines ?? res?.items ?? (Array.isArray(res) ? res : []);
    },
  });

  // Derive the active pipeline: user selection → default → first available
  const activePipelineId =
    selectedPipelineId ?? pipelines.find((p) => p.is_default)?.id ?? pipelines[0]?.id ?? null;

  const { data: customerHits } = useQuery({
    queryKey: ['customers', 'search', debouncedCustomerQuery],
    enabled: debouncedCustomerQuery.length >= 2,
    queryFn: async () => {
      const res = await customersApi.getCustomers({ q: debouncedCustomerQuery, limit: 20 });
      return res.items as Customer[];
    },
  });

  const { data: kanban, isLoading } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey: ['board', 'kanban', activePipelineId, customerId, minRottingDays, minOpenTasks],
    queryFn: () => {
      const params: Record<string, unknown> = {};
      if (activePipelineId != null) params.pipeline_id = activePipelineId;
      if (customerId !== '') params.customer_id = customerId;
      if (minRottingDays > 0) params.min_rotting_days = minRottingDays;
      if (minOpenTasks > 0) params.min_open_tasks = minOpenTasks;
      return boardApi.getKanban(Object.keys(params).length ? params : undefined);
    },
  });

  const { data: summary } = useQuery<BoardSummary>({
    queryKey: ['board', 'summary'],
    queryFn: () => boardApi.getSummary(30),
  });

  const { data: healthOverview } = useQuery<{ opportunities: DealHealthReport[] }>({
    queryKey: ['deal-health', 'overview'],
    queryFn: () => dealHealthApi.getOverview(),
    retry: false,
    staleTime: 60_000,
  });

  const { data: highIntent } = useQuery<HighIntentListResponse>({
    queryKey: ['high-intent-accounts', 'board-widget'],
    queryFn: () => customersApi.listHighIntent({ limit: 5 }) as Promise<HighIntentListResponse>,
    staleTime: 60_000,
    retry: false,
  });

  const healthMap = useMemo(() => {
    const map = new Map<number, { score: number; risk_level: string }>();
    if (healthOverview?.opportunities) {
      for (const deal of healthOverview.opportunities) {
        map.set(deal.opportunity_id, {
          score: deal.score,
          risk_level: deal.risk_level,
        });
      }
    }
    return map;
  }, [healthOverview]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  const columns = kanban?.columns || [];
  const riskRank = (riskLevel: string | null | undefined): number => {
    switch (riskLevel) {
      case 'critical':
        return 4;
      case 'high_risk':
        return 3;
      case 'at_risk':
        return 2;
      case 'healthy':
        return 1;
      default:
        return 0;
    }
  };

  return (
    <div>
      <PageHeader title="Sales Board" description="Pipeline gorunumu" />

      {/* Pipeline selector — only shown when multiple pipelines exist */}
      {pipelines.length > 1 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {pipelines.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setSelectedPipelineId(p.id)}
              className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-colors ${
                activePipelineId === p.id
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
              }`}
            >
              {p.name}
              {p.is_default && <span className="ml-1.5 text-[10px] opacity-70">★</span>}
            </button>
          ))}
        </div>
      )}

      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              Müşteri
              <input
                value={customerQuery}
                onChange={(e) => {
                  setCustomerQuery(e.target.value);
                  setCustomerId('');
                }}
                placeholder="İsim / şirket ara (≥2 harf)"
                className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              />
              <select
                className="mt-2 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                value={customerId === '' ? '' : String(customerId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setCustomerId(v === '' ? '' : Number(v));
                }}
                disabled={!customerHits || customerHits.length === 0}
              >
                <option value="">
                  {debouncedCustomerQuery.length < 2 ? 'Aramak için yazın…' : 'Seçin…'}
                </option>
                {(customerHits ?? []).map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.name}
                    {c.company ? ` — ${c.company}` : ''}
                  </option>
                ))}
              </select>
            </label>

            <label className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              Min. bayatlık (gün)
              <input
                type="number"
                min={0}
                value={minRottingDays}
                onChange={(e) => setMinRottingDays(Number(e.target.value || 0))}
                className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              />
            </label>

            <label className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              Min. açık task
              <input
                type="number"
                min={0}
                value={minOpenTasks}
                onChange={(e) => setMinOpenTasks(Number(e.target.value || 0))}
                className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              />
            </label>

            <label className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              Fırsat riski (client)
              <select
                value={dealHealthRisk}
                onChange={(e) => setDealHealthRisk(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              >
                <option value="">Tümü</option>
                <option value="critical">Kritik</option>
                <option value="high_risk">Yüksek risk</option>
                <option value="at_risk">Risk altında</option>
                <option value="healthy">Sağlıklı</option>
              </select>
            </label>
          </div>

          <button
            type="button"
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
            onClick={() => {
              setMinRottingDays(0);
              setMinOpenTasks(0);
              setCustomerId('');
              setCustomerQuery('');
              setDealHealthRisk('');
            }}
          >
            Sıfırla
          </button>
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          {t('board.server_filters_hint')}
        </p>
      </div>

      {/* High-intent accounts (Salesforce parity widget) */}
      <div className="mb-6 rounded-xl border border-amber-200/80 bg-gradient-to-br from-amber-50/90 to-white p-4 shadow-sm dark:border-amber-900/40 dark:from-amber-950/30 dark:to-gray-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-amber-700 dark:text-amber-400" aria-hidden />
            <div>
              <p className="text-sm font-bold text-gray-900 dark:text-white">
                {t('board.high_intent_title')}
              </p>
              <p className="text-xs text-gray-600 dark:text-gray-400">
                {t('board.high_intent_sub')}
              </p>
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => navigate('/customers/high-intent')}>
            {t('board.high_intent_cta')}
          </Button>
        </div>
        {!highIntent?.items?.length ? (
          <p className="text-xs text-gray-500 dark:text-gray-400">{t('board.high_intent_empty')}</p>
        ) : (
          <ul className="divide-y divide-amber-100 dark:divide-amber-900/30">
            {highIntent.items.map((row) => (
              <li key={row.customer_id}>
                <button
                  type="button"
                  onClick={() => navigate(`/customers/${row.customer_id}`)}
                  className="flex w-full items-center justify-between gap-2 py-2 text-left text-sm hover:bg-amber-100/50 dark:hover:bg-amber-950/40 rounded-lg px-1 -mx-1"
                >
                  <span className="min-w-0 truncate font-medium text-honeywell-red">
                    {row.company || row.name}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {row.pinned && (
                      <Badge variant="default" size="sm">
                        ★
                      </Badge>
                    )}
                    <span className="text-xs text-gray-500">{row.score}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* KPI bar */}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                Acik Pipeline
              </p>
              <p className="mt-1 text-2xl font-extrabold text-blue-700 dark:text-blue-400">
                {formatCurrency(summary.open_pipeline_total, 'TRY')}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                Kazanma Orani
              </p>
              <p className="mt-1 text-2xl font-extrabold text-green-700 dark:text-green-400">
                %{summary.win_rate}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">Kazanilan</p>
              <p className="mt-1 text-2xl font-extrabold text-gray-900 dark:text-white">
                {summary.won_count}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                Curume (Rotting)
              </p>
              <p
                className={`mt-1 text-2xl font-extrabold ${summary.rotting_count > 0 ? 'text-red-700 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}
              >
                {summary.rotting_count}
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* Kanban board */}
      <div className="flex gap-4 overflow-x-auto pb-4">
        {columns.map((col) => (
          <div key={col.stage} className="min-w-[280px] shrink-0">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-bold ${STAGE_COLORS[col.stage] || 'bg-gray-200 text-gray-800'}`}
                >
                  {STAGE_LABELS[col.stage] || col.stage}
                </span>
                <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs font-bold text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                  {(() => {
                    const visible = dealHealthRisk
                      ? col.items.filter((o) => healthMap.get(o.id)?.risk_level === dealHealthRisk)
                      : col.items;
                    return visible.length;
                  })()}
                </span>
              </div>
              <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                {(() => {
                  const visible = dealHealthRisk
                    ? col.items.filter((o) => healthMap.get(o.id)?.risk_level === dealHealthRisk)
                    : col.items;
                  const total = visible.reduce(
                    (sum, o) => sum + (typeof o.amount === 'number' ? o.amount : 0),
                    0,
                  );
                  return formatCurrency(total, 'TRY');
                })()}
              </span>
            </div>
            <div className="space-y-2 rounded-xl bg-gray-50 p-2 dark:bg-gray-900/50 min-h-[200px]">
              {(() => {
                const visible = dealHealthRisk
                  ? col.items.filter((o) => healthMap.get(o.id)?.risk_level === dealHealthRisk)
                  : col.items;
                if (visible.length === 0) {
                  return <p className="py-8 text-center text-xs text-gray-400">Fırsat yok</p>;
                }
                return [...visible]
                  .sort((a, b) => {
                    const ar = riskRank(healthMap.get(a.id)?.risk_level);
                    const br = riskRank(healthMap.get(b.id)?.risk_level);
                    if (br !== ar) return br - ar;
                    if (b.rotting_days !== a.rotting_days) return b.rotting_days - a.rotting_days;
                    return b.id - a.id;
                  })
                  .map((opp) => (
                    <KanbanCard
                      key={opp.id}
                      opp={opp}
                      healthScore={healthMap.get(opp.id) ?? null}
                    />
                  ));
              })()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
