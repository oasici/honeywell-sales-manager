import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Target, Star, RotateCcw, ListChecks, Activity } from 'lucide-react';
import { boardApi, customersApi, dealHealthApi, pipelinesApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { Skeleton } from '../../components/ui/Skeleton';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
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

/* ─────────────────────── Stage tokens ─────────────────────── */

const STAGE_LABELS: Record<string, string> = {
  prospecting: 'Araştırma',
  qualified: 'Nitelenmiş',
  proposal: 'Teklif',
  negotiation: 'Müzakere',
  closed_won: 'Kazanıldı',
  closed_lost: 'Kaybedildi',
};

/**
 * Stage color tokens for the column heading.
 *
 * - dot:     6×6 leading dot (status indicator)
 * - chip:    pill backing for the stage label
 * Closed states (won/lost) get the strongest visual weight; in-flight
 * stages stay calmer so the board doesn't feel like a traffic light.
 */
const STAGE_TONE: Record<string, { dot: string; chip: string }> = {
  prospecting: {
    dot: 'bg-slate-400',
    chip: 'bg-slate-100 text-slate-700 ring-slate-200',
  },
  qualified: {
    dot: 'bg-blue-500',
    chip: 'bg-blue-50 text-blue-700 ring-blue-100',
  },
  proposal: {
    dot: 'bg-amber-500',
    chip: 'bg-amber-50 text-amber-800 ring-amber-100',
  },
  negotiation: {
    dot: 'bg-orange-500',
    chip: 'bg-orange-50 text-orange-800 ring-orange-100',
  },
  closed_won: {
    dot: 'bg-emerald-500',
    chip: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  },
  closed_lost: {
    dot: 'bg-red-500',
    chip: 'bg-red-50 text-red-700 ring-red-100',
  },
};

// Round-10 R10-FE-13 — explicit type narrowing: the prospecting key is
// always present in STAGE_TONE so `!` is safe and lets downstream code
// treat FALLBACK_TONE as a non-undefined value.
const FALLBACK_TONE = STAGE_TONE.prospecting!;

/* ─────────────────────── KanbanCard ─────────────────────── */

/**
 * Forecast-category pill tones. Mirrors the four ForecastCategory enum
 * values returned by the backend; ``commit`` gets the strongest weight
 * so it stands out at a glance, ``omitted`` is muted because it's
 * excluded from forecast rollups.
 */
const FORECAST_CATEGORY_TONE: Record<string, string> = {
  commit:
    'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40',
  best_case:
    'bg-blue-50 text-blue-700 ring-blue-100 dark:bg-blue-950/30 dark:text-blue-400 dark:ring-blue-900/40',
  pipeline:
    'bg-slate-50 text-slate-600 ring-slate-200 dark:bg-slate-900/40 dark:text-slate-400 dark:ring-slate-800',
  omitted:
    'bg-slate-50 text-slate-400 ring-slate-100 dark:bg-slate-900/40 dark:text-slate-500 dark:ring-slate-800',
};

const FORECAST_CATEGORY_LABEL: Record<string, string> = {
  commit: 'Commit',
  best_case: 'Best',
  pipeline: 'Pipe',
  omitted: 'Omit',
};

/**
 * Coerce ``probability`` (0-1 or 0-100) to a percent integer suitable
 * for display. The backend has historically been inconsistent here so
 * we accept either shape. Returns ``null`` when probability is absent.
 */
function probabilityPct(prob: number | undefined): number | null {
  if (prob == null) return null;
  if (prob <= 1) return Math.round(prob * 100);
  return Math.round(prob);
}

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

  const isRotting = opp.rotting_days > 7;
  const probPct = probabilityPct(opp.probability);
  const isClosedLost = opp.status === 'closed_lost';

  return (
    <button
      type="button"
      onClick={() => navigate(`/opportunities/${opp.id}`)}
      className="group w-full rounded-xl border border-slate-200 bg-white p-3 text-left shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 truncate text-[13px] font-semibold text-slate-900 dark:text-white">
          {opp.title}
        </p>
        {/* R5-RENDER-OPP-1 — forecast_category pill. Hidden when null
            so cards without a category stay visually quieter. */}
        {opp.forecast_category && (
          <span
            className={[
              'shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ring-1 ring-inset',
              FORECAST_CATEGORY_TONE[opp.forecast_category] ?? FORECAST_CATEGORY_TONE.pipeline,
            ].join(' ')}
            title={`Forecast: ${opp.forecast_category}`}
          >
            {FORECAST_CATEGORY_LABEL[opp.forecast_category] ?? opp.forecast_category}
          </span>
        )}
      </div>
      {opp.customer && (
        <p className="mt-0.5 truncate text-[12px] text-slate-500 dark:text-slate-400">
          {opp.customer.name}
        </p>
      )}
      {/* R5-RENDER-OPP-1 — loss_reason is only meaningful when the
          deal is closed_lost; suppressing on other statuses prevents
          stale text from cluttering open-deal cards. */}
      {isClosedLost && opp.loss_reason && (
        <p
          className="mt-0.5 truncate text-[11px] italic text-red-600 dark:text-red-400"
          title={opp.loss_reason}
        >
          {opp.loss_reason}
        </p>
      )}

      <div className="mt-2.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {opp.amount != null ? (
            <span className="text-[14px] font-bold tabular-nums text-slate-900 dark:text-white">
              {formatCurrency(opp.amount, opp.currency)}
            </span>
          ) : (
            <span className="text-[12px] text-slate-400">—</span>
          )}
          {/* R5-RENDER-OPP-1 — show probability as % next to amount. */}
          {probPct != null && (
            <span className="text-[11px] font-medium tabular-nums text-slate-500 dark:text-slate-400">
              {probPct}%
            </span>
          )}
          {healthScore && (
            <DealHealthBadge score={healthScore.score} riskLevel={healthScore.risk_level} />
          )}
        </div>
        {isRotting && (
          <Badge variant="danger" size="sm" dot>
            {opp.rotting_days}g
          </Badge>
        )}
      </div>
      {/* R6-RENDER-OPP-1 — surface revenue slip ("$50k → $30k") inline
          on the kanban so managers can scan slippage without opening
          each deal. Same data was visible on the detail page only. */}
      {opp.previous_amount != null && opp.previous_amount !== opp.amount && (
        <p
          className="mt-1 flex items-center gap-1 text-[11px] font-medium tabular-nums text-amber-600 dark:text-amber-400"
          title={t('board.amount_changed_tooltip')}
        >
          <span className="opacity-60 line-through">
            {formatCurrency(opp.previous_amount, opp.currency)}
          </span>
          <span aria-hidden>→</span>
          <span>{opp.amount != null ? formatCurrency(opp.amount, opp.currency) : '—'}</span>
        </p>
      )}
      {/* R6-RENDER-OPP-1 — close-date slip indicator. */}
      {opp.previous_close_date && opp.previous_close_date !== opp.close_date && (
        <p
          className="mt-0.5 text-[10px] text-amber-600 dark:text-amber-400"
          title="Kapanış tarihi değişti"
        >
          Kapanış: {opp.previous_close_date} → {opp.close_date ?? '—'}
        </p>
      )}
      {/* R6-RENDER-OPP-1 — pipeline/territory chips for cross-filter
          scans. Tiny so they don't crowd the card. */}
      {(opp.pipeline_id != null || opp.territory_id != null) && (
        <div className="mt-1 flex flex-wrap gap-1">
          {opp.pipeline_id != null && (
            <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-slate-600 dark:bg-slate-800 dark:text-slate-400">
              P-{opp.pipeline_id}
            </span>
          )}
          {opp.territory_id != null && (
            <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-slate-600 dark:bg-slate-800 dark:text-slate-400">
              T-{opp.territory_id}
            </span>
          )}
        </div>
      )}

      {(opp.open_tasks_count || lastActivityDays != null || opp.owner || opp.source) && (
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 dark:border-slate-800">
          <div className="flex min-w-0 items-center gap-2 text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
            {typeof opp.open_tasks_count === 'number' && opp.open_tasks_count > 0 && (
              <span className="inline-flex items-center gap-1">
                <ListChecks size={11} className="text-slate-400" />
                {opp.open_tasks_count}
              </span>
            )}
            {typeof lastActivityDays === 'number' && (
              <span title={t('board.rotting_tooltip')} className="inline-flex items-center gap-1">
                <Activity size={11} className="text-slate-400" />
                {t('board.last_activity_fmt').replace('{{d}}', String(lastActivityDays))}
              </span>
            )}
            {/* R5-RENDER-OPP-1 — small source hint (lead-source
                attribution). Truncated to keep the meta row tidy. */}
            {opp.source && (
              <span
                className="truncate text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500"
                title={`Source: ${opp.source}`}
              >
                {opp.source}
              </span>
            )}
          </div>
          {opp.owner && (
            <p className="truncate text-[11px] text-slate-400 dark:text-slate-500">
              {opp.owner.full_name}
            </p>
          )}
        </div>
      )}
    </button>
  );
}

/* ─────────────────────── KpiTile ─────────────────────── */

interface KpiTileProps {
  label: string;
  value: string;
  tone?: 'default' | 'positive' | 'negative';
}

function KpiTile({ label, value, tone = 'default' }: KpiTileProps) {
  const valueClass =
    tone === 'positive'
      ? 'text-emerald-600 dark:text-emerald-400'
      : tone === 'negative'
        ? 'text-red-600 dark:text-red-400'
        : 'text-slate-900 dark:text-white';
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <p className="text-overline text-slate-500 dark:text-slate-400">{label}</p>
      <p
        className={`mt-2 text-[24px] font-bold leading-none tracking-tight tabular-nums ${valueClass}`}
      >
        {value}
      </p>
    </div>
  );
}

/* ─────────────────────── Page ─────────────────────── */

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
    const tm = window.setTimeout(() => setDebouncedCustomerQuery(customerQuery.trim()), 300);
    return () => window.clearTimeout(tm);
  }, [customerQuery]);

  const { data: pipelines = [] } = useQuery<Pipeline[]>({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await pipelinesApi.list();
      // Round-5 Phase 7 — backend canonicalized to ``items``; legacy
      // ``pipelines`` retained server-side as additive bridge.
      return res?.items ?? res?.pipelines ?? (Array.isArray(res) ? res : []);
    },
  });

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

  // Round-15 Sprint 15h — surface kanban load failure so an outage
  // renders a retry banner instead of an empty board.
  const {
    data: kanban,
    isLoading,
    isError: kanbanIsError,
    refetch: refetchKanban,
  } = useQuery<{ columns: KanbanColumn[] }>({
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

  // Round-15 Sprint 15i — surface isError on the three secondary
  // board widgets so a partial outage doesn't silently render empty
  // tiles. The kanban error already short-circuits the whole page
  // above; these are the smaller side widgets that fail independently.
  const {
    data: summary,
    isError: summaryIsError,
    refetch: refetchSummary,
  } = useQuery<BoardSummary>({
    queryKey: ['board', 'summary'],
    queryFn: () => boardApi.getSummary(30),
  });

  // healthOverview is consumed only to build the dealHealthRisk filter
  // map below; no visible panel, so isError is left as silent.
  const { data: healthOverview } = useQuery<{ opportunities: DealHealthReport[] }>({
    queryKey: ['deal-health', 'overview'],
    queryFn: () => dealHealthApi.getOverview(),
    retry: false,
    staleTime: 60_000,
  });

  const {
    data: highIntent,
    isError: highIntentIsError,
    refetch: refetchHighIntent,
  } = useQuery<HighIntentListResponse>({
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
      <div>
        <PageHeader title="Sales Board" description="Pipeline görünümü" />
        <div className="space-y-4">
          <Skeleton variant="card" count={3} />
        </div>
      </div>
    );
  }

  // Round-15 Sprint 15h — distinguish "kanban failed to load" from
  // "no opportunities in pipeline". Pre-fix, an outage rendered as
  // an empty board with no retry affordance.
  if (kanbanIsError) {
    return (
      <div>
        <PageHeader title="Sales Board" description="Pipeline görünümü" />
        <QueryErrorBanner variant="block" onRetry={() => refetchKanban()} />
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

  const customerOptions = [
    {
      value: '',
      label: debouncedCustomerQuery.length < 2 ? t('common.search_typing_hint') : t('common.choose'),
    },
    ...(customerHits ?? []).map((c) => ({
      value: String(c.id),
      label: `${c.name}${c.company ? ` — ${c.company}` : ''}`,
    })),
  ];

  const riskOptions = [
    { value: '', label: 'Tümü' },
    { value: 'critical', label: 'Kritik' },
    { value: 'high_risk', label: 'Yüksek risk' },
    { value: 'at_risk', label: 'Risk altında' },
    { value: 'healthy', label: 'Sağlıklı' },
  ];

  return (
    <div>
      <PageHeader title="Sales Board" description="Pipeline görünümü ve fırsat sağlığı" />

      {/* Pipeline selector — segmented tabs (matches QuoteListPage). Only
          shown when multiple pipelines exist; the default pipeline gets a
          star marker. */}
      {pipelines.length > 1 && (
        <div
          className="mb-4 inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
          role="tablist"
          aria-label="Pipeline seçimi"
        >
          {pipelines.map((p) => {
            const isActive = activePipelineId === p.id;
            return (
              <button
                key={p.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setSelectedPipelineId(p.id)}
                className={[
                  'inline-flex h-8 items-center gap-1.5 rounded-[10px] px-3 text-[13px] font-medium transition-all',
                  'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                  isActive
                    ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
                    : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
                ].join(' ')}
              >
                {p.name}
                {p.is_default && <Star size={11} className="text-amber-500" fill="currentColor" />}
              </button>
            );
          })}
        </div>
      )}

      {/* Filter card */}
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-1">
            <Input
              label={t('common.search_customer')}
              placeholder="İsim / şirket (≥2 harf)"
              value={customerQuery}
              onChange={(e) => {
                setCustomerQuery(e.target.value);
                setCustomerId('');
              }}
            />
            <div className="mt-2">
              <Select
                options={customerOptions}
                value={customerId === '' ? '' : String(customerId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setCustomerId(v === '' ? '' : Number(v));
                }}
                disabled={!customerHits || customerHits.length === 0}
              />
            </div>
          </div>

          <Input
            label="Min. bayatlık (gün)"
            type="number"
            min={0}
            value={minRottingDays}
            onChange={(e) => setMinRottingDays(Number(e.target.value || 0))}
          />

          <Input
            label="Min. açık task"
            type="number"
            min={0}
            value={minOpenTasks}
            onChange={(e) => setMinOpenTasks(Number(e.target.value || 0))}
          />

          <Select
            label="Fırsat riski (client)"
            options={riskOptions}
            value={dealHealthRisk}
            onChange={(e) => setDealHealthRisk(e.target.value)}
          />
        </div>
        <div className="mt-4 flex items-center justify-between">
          <p className="text-[12px] text-slate-500 dark:text-slate-400">
            {t('board.server_filters_hint')}
          </p>
          <Button
            variant="tertiary"
            size="sm"
            onClick={() => {
              setMinRottingDays(0);
              setMinOpenTasks(0);
              setCustomerId('');
              setCustomerQuery('');
              setDealHealthRisk('');
            }}
          >
            <RotateCcw size={13} />
            {t('common.reset')}
          </Button>
        </div>
      </div>

      {/* High-intent accounts widget */}
      <div className="mb-6 overflow-hidden rounded-2xl border border-amber-100 bg-linear-to-br from-amber-50/70 to-transparent shadow-(--shadow-xs) dark:border-amber-900/40 dark:from-amber-950/20">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-100/80 px-5 py-4 dark:border-amber-900/40">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
              <Target size={16} />
            </span>
            <div>
              <p className="text-[13px] font-semibold text-slate-900 dark:text-white">
                {t('board.high_intent_title')}
              </p>
              <p className="text-[12px] text-slate-500 dark:text-slate-400">
                {t('board.high_intent_sub')}
              </p>
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => navigate('/customers/high-intent')}>
            {t('board.high_intent_cta')}
          </Button>
        </div>
        {highIntentIsError ? (
          <div className="px-5 py-3">
            <QueryErrorBanner onRetry={() => refetchHighIntent()} />
          </div>
        ) : !highIntent?.items?.length ? (
          <p className="px-5 py-4 text-[12px] text-slate-500 dark:text-slate-400">
            {t('board.high_intent_empty')}
          </p>
        ) : (
          <ul className="divide-y divide-amber-100/60 dark:divide-amber-900/30">
            {highIntent.items.map((row) => (
              <li key={row.customer_id}>
                <button
                  type="button"
                  onClick={() => navigate(`/customers/${row.customer_id}`)}
                  className="group flex w-full items-center justify-between gap-3 px-5 py-2.5 text-left transition-colors hover:bg-amber-50/60 dark:hover:bg-amber-950/30"
                >
                  <span className="min-w-0 truncate text-[13px] font-medium text-slate-900 dark:text-white">
                    {row.company || row.name}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {row.pinned && (
                      <Badge variant="warning" size="sm">
                        <Star size={10} fill="currentColor" />
                        Sabitli
                      </Badge>
                    )}
                    <span className="inline-flex h-6 min-w-[40px] items-center justify-center rounded-full bg-amber-100 px-2 text-[11px] font-bold tabular-nums text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
                      {row.score}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* KPI strip */}
      {summaryIsError && (
        <div className="mb-6">
          <QueryErrorBanner onRetry={() => refetchSummary()} />
        </div>
      )}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KpiTile
            label="Açık Pipeline"
            value={formatCurrency(summary.open_pipeline_total, 'TRY')}
          />
          <KpiTile label="Kazanma Oranı" value={`%${summary.win_rate}`} tone="positive" />
          <KpiTile label="Kazanılan" value={String(summary.won_count)} />
          <KpiTile
            label="Çürüme (Rotting)"
            value={String(summary.rotting_count)}
            tone={summary.rotting_count > 0 ? 'negative' : 'default'}
          />
        </div>
      )}

      {/* Kanban board — horizontal scroll on overflow. Each column has a
          slate-50 well so cards visually belong to the column even when the
          board scrolls horizontally. */}
      <div className="flex gap-4 overflow-x-auto pb-4">
        {columns.map((col) => {
          const tone = STAGE_TONE[col.stage] ?? FALLBACK_TONE;
          const visible = dealHealthRisk
            ? col.items.filter((o) => healthMap.get(o.id)?.risk_level === dealHealthRisk)
            : col.items;
          const total = visible.reduce(
            (sum, o) => sum + (typeof o.amount === 'number' ? o.amount : 0),
            0,
          );

          return (
            <div key={col.stage} className="min-w-[300px] shrink-0">
              {/* Column header */}
              <div className="mb-3 flex items-center justify-between">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className={[
                      'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ring-1 ring-inset',
                      tone.chip,
                    ].join(' ')}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${tone.dot}`} />
                    {STAGE_LABELS[col.stage] || col.stage}
                  </span>
                  <span className="inline-flex h-5 min-w-[22px] items-center justify-center rounded-full bg-slate-100 px-1.5 text-[11px] font-bold tabular-nums text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                    {visible.length}
                  </span>
                </div>
                <span className="text-[12px] font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                  {formatCurrency(total, 'TRY')}
                </span>
              </div>

              {/* Card stack */}
              <div className="min-h-[200px] space-y-2 rounded-2xl border border-slate-200 bg-slate-50/60 p-2 dark:border-slate-800 dark:bg-slate-900/40">
                {visible.length === 0 ? (
                  <p className="py-10 text-center text-[12px] text-slate-400">
                    {t('common.no_opportunities')}
                  </p>
                ) : (
                  [...visible]
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
                    ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
