import { useState, useCallback, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { EmailSetupModal } from '../auth/EmailSetupModal';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, rectSortingStrategy, arrayMove } from '@dnd-kit/sortable';
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { Skeleton } from '../../components/ui/Skeleton';
import { SafeChart } from '../../components/ui/SafeChart';
import { PageHeader } from '../../components/ui/PageHeader';
import { EmptyState } from '../../components/ui/EmptyState';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import {
  Phone,
  Handshake,
  Mail,
  FileText,
  Zap,
  AlertCircle,
  FileWarning,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import { dashboardApi, analyticsApi, subscriptionsApi, activitiesApi } from '../../lib/api';
import { formatCurrency, formatRelativeTime } from '../../lib/formatters';
import type {
  DashboardStats,
  TopPart,
  TrendData,
  MrrDashboard,
  ActivityLogEntry,
} from '../../lib/types';
import { AtRiskCustomersCard } from './AtRiskCustomersCard';
import { KpiCard } from './KpiCard';
import { DoughnutChart } from './DoughnutChart';
import { SortableItem } from './SortableItem';
import { LeaderboardCard } from './LeaderboardCard';

// Round-10 R10-FE-8 — local Turkish-only formatter replaced by the
// locale-aware `formatRelativeTime` in lib/formatters.ts (uses
// Intl.RelativeTimeFormat against the active preferences locale).

/* ─────────────────── localStorage helpers ─────────────────── */
// Round-10 R10-FE-6 — legacy key "dash-seç" was renamed to "dash-sections"
// in v1.16.0; once a returning user lands and writes the new key, the old
// row stays as an orphan in localStorage until cleared. The single-key
// shim below keeps the section order across the rename.
const LEGACY_KEY_MAP: Record<string, string> = {
  'dash-sections': 'dash-seç',
};

// Round-12 R12-FE-2 — SSR guard. `loadOrder` is called inside
// `useState` initializers at first render; without this guard the
// page crashes during Node-side render (`localStorage is not
// defined`). Returns the fallback during SSR; the real value
// hydrates client-side on first effect.
const HAS_STORAGE = typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';

function loadOrder(key: string, fallback: string[]): string[] {
  if (!HAS_STORAGE) return fallback;
  try {
    const s = localStorage.getItem(key);
    if (s) return JSON.parse(s);
    const legacy = LEGACY_KEY_MAP[key];
    if (legacy) {
      const legacyValue = localStorage.getItem(legacy);
      if (legacyValue) {
        // One-time migration: copy across, drop the legacy row.
        localStorage.setItem(key, legacyValue);
        localStorage.removeItem(legacy);
        return JSON.parse(legacyValue);
      }
    }
    return fallback;
  } catch {
    return fallback;
  }
}

function safeSaveOrder(key: string, value: string[]): void {
  if (!HAS_STORAGE) return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage quota or disabled — drop silently */
  }
}

/* ─────────────────── DEFAULT ORDERS ─────────────────── */
const DEFAULT_KPI = [
  'total_emails',
  'total_quotes',
  'total_parts',
  'total_customers',
  'conversion_rate',
  'pending_review',
];
const DEFAULT_DOUGHNUTS = ['d_mail', 'd_value', 'd_count', 'd_quote'];
const DEFAULT_SECTIONS = [
  'doughnuts',
  'at_risk_customers',
  'leaderboard',
  'mrr_overview',
  'top_parts',
  'trends',
  'data_quality',
  'action_required',
  'activity_feed',
];

/* ─────────────────── MAIN ─────────────────── */
export default function DashboardPage() {
  const navigate = useNavigate();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const [kpiOrder, setKpiOrder] = useState(() => loadOrder('dash-kpi', DEFAULT_KPI));
  const [doughnutOrder, setDoughnutOrder] = useState(() =>
    loadOrder('dash-donut', DEFAULT_DOUGHNUTS),
  );
  // Round-10 R10-FE-6 — key renamed from "dash-seç" (Turkish for "choose") to
  // the ASCII-only "dash-sections". `loadOrder` falls back to the legacy key
  // once for users mid-migration; tracked via `_legacy_section_key` migration
  // probe below to drop in v1.17.x.
  const [secOrder, setSecOrder] = useState(() => loadOrder('dash-sections', DEFAULT_SECTIONS));

  /* ── Email setup popup (first login only) ── */
  const user = useAuthStore((s) => s.user);
  const [showEmailSetup, setShowEmailSetup] = useState(() =>
    Boolean(user && !user.email_setup_completed),
  );

  /* ── data ── */
  const {
    data: stats,
    isLoading,
    isError,
    refetch,
  } = useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: dashboardApi.getStats,
  });
  const { data: topParts } = useQuery<TopPart[]>({
    queryKey: ['top-parts'],
    queryFn: () => analyticsApi.getTopParts(30, 10),
  });
  const { data: dataQuality } = useQuery<{ data: { avg_score: number } }>({
    queryKey: ['data-quality-overview'],
    queryFn: () => analyticsApi.getDataQuality(),
  });
  const { data: mrrDashboard } = useQuery<MrrDashboard>({
    queryKey: ['subscriptions', 'mrr-dashboard'],
    queryFn: () => subscriptionsApi.getMrrDashboard(),
  });
  const { data: trend } = useQuery<TrendData[]>({
    queryKey: ['monthly-trend'],
    queryFn: () => analyticsApi.getMonthlyTrend(6),
  });
  const { data: activityFeed } = useQuery<ActivityLogEntry[]>({
    queryKey: ['activity-feed'],
    queryFn: () => activitiesApi.getFeed({ limit: 30 }),
    refetchInterval: 30000,
  });

  /* ── drag handlers ── */
  const onKpiDrag = useCallback((e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setKpiOrder((prev) => {
      const next = arrayMove(
        prev,
        prev.indexOf(active.id as string),
        prev.indexOf(over.id as string),
      );
      safeSaveOrder('dash-kpi', next);
      return next;
    });
  }, []);

  const onDoughnutDrag = useCallback((e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setDoughnutOrder((prev) => {
      const next = arrayMove(
        prev,
        prev.indexOf(active.id as string),
        prev.indexOf(over.id as string),
      );
      safeSaveOrder('dash-donut', next);
      return next;
    });
  }, []);

  const onSecDrag = useCallback((e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setSecOrder((prev) => {
      const next = arrayMove(
        prev,
        prev.indexOf(active.id as string),
        prev.indexOf(over.id as string),
      );
      safeSaveOrder('dash-sections', next);
      return next;
    });
  }, []);

  /* ── error ── */
  if (isError) {
    return (
      <div>
        <PageHeader
          title="Kontrol Paneli"
          description="Boru hattı, müşteri sağlığı ve ekip performansı tek panelde."
        />
        <QueryErrorBanner variant="block" onRetry={() => refetch()} />
      </div>
    );
  }

  /* ── loading ── */
  if (isLoading || !stats) {
    return (
      <div>
        <PageHeader
          title="Kontrol Paneli"
          description="Boru hattı, müşteri sağlığı ve ekip performansı tek panelde."
        />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-[88px] rounded-2xl" />
          ))}
        </div>
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-56 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  /* ── KPI map ── */
  const s = {
    total_emails: stats.total_emails ?? 0,
    total_quotes: stats.total_quotes ?? 0,
    total_parts: stats.total_parts ?? 0,
    total_customers: stats.total_customers ?? 0,
    conversion_rate: stats.conversion_rate ?? 0,
    pending_review_count: stats.pending_review_count ?? 0,
    pending_value: stats.pending_value ?? 0,
    answered_emails: stats.answered_emails ?? 0,
    total_parts_value: stats.total_parts_value ?? 0,
    answered_parts_value: stats.answered_parts_value ?? 0,
    total_parts_count: stats.total_parts_count ?? 0,
    answered_parts_count: stats.answered_parts_count ?? 0,
    approved_quotes: stats.approved_quotes ?? 0,
  };

  const kpiMap: Record<string, ReactNode> = {
    total_emails: (
      <KpiCard label="Toplam Mail" value={s.total_emails} onClick={() => navigate('/emails')} />
    ),
    total_quotes: (
      <KpiCard label="Toplam Teklif" value={s.total_quotes} onClick={() => navigate('/quotes')} />
    ),
    total_parts: (
      <KpiCard label="Toplam Parça" value={s.total_parts} onClick={() => navigate('/parts')} />
    ),
    total_customers: (
      <KpiCard
        label="Toplam Müşteri"
        value={s.total_customers}
        onClick={() => navigate('/customers')}
      />
    ),
    conversion_rate: <KpiCard label="Donusum Orani" value={`%${s.conversion_rate}`} />,
    pending_review: (
      <KpiCard
        label="İnceleme Bekleyen"
        value={s.pending_review_count}
        onClick={() => navigate('/emails?review=pending_review')}
      />
    ),
  };

  /* ── section map ── */
  const secMap: Record<string, ReactNode> = {
    doughnuts: (() => {
      const doughnutMap: Record<string, ReactNode> = {
        d_mail: (
          <DoughnutChart
            title="Cevaplanan Mail Orani"
            filled={s.answered_emails}
            total={s.total_emails}
            colorIndex={0}
          />
        ),
        d_value: (
          <DoughnutChart
            title="Cevaplanan Parça Degeri"
            filled={s.answered_parts_value}
            total={s.total_parts_value}
            unit="USD"
            colorIndex={1}
          />
        ),
        d_count: (
          <DoughnutChart
            title="Cevaplanan Parça Sayisi"
            filled={s.answered_parts_count}
            total={s.total_parts_count}
            unit="adet"
            colorIndex={2}
          />
        ),
        d_quote: (
          <DoughnutChart
            title="Onaylanan Teklif Orani"
            filled={s.approved_quotes}
            total={s.total_quotes}
            colorIndex={3}
          />
        ),
      };
      return (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-4 text-overline text-slate-500 dark:text-slate-400">
            Performans Metrikleri
          </h3>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={onDoughnutDrag}
          >
            <SortableContext items={doughnutOrder} strategy={rectSortingStrategy}>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {doughnutOrder.map((id) => (
                  <SortableItem key={id} id={id}>
                    {doughnutMap[id]}
                  </SortableItem>
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </div>
      );
    })(),

    at_risk_customers: <AtRiskCustomersCard />,

    leaderboard: <LeaderboardCard />,

    data_quality: (
      <button
        type="button"
        className="group flex w-full items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-800 dark:bg-slate-900"
        onClick={() => navigate('/admin/data-quality')}
      >
        <div className="relative h-16 w-16 shrink-0">
          <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90" aria-hidden="true">
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e2e8f0" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r="15.5"
              fill="none"
              stroke={
                (dataQuality?.data?.avg_score ?? 0) >= 75
                  ? '#10b981'
                  : (dataQuality?.data?.avg_score ?? 0) >= 50
                    ? '#f59e0b'
                    : '#ef4444'
              }
              strokeWidth="3"
              strokeDasharray={`${dataQuality?.data?.avg_score ?? 0} ${100 - (dataQuality?.data?.avg_score ?? 0)}`}
              strokeLinecap="round"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-[15px] font-bold tabular-nums text-slate-900 dark:text-white">
            {Math.round(dataQuality?.data?.avg_score ?? 0)}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-overline text-slate-500 dark:text-slate-400">Veri Kalitesi</p>
          <p className="mt-1 text-[13px] font-medium text-slate-700 dark:text-slate-300">
            Genel veri kalite puanı
          </p>
          <p className="mt-0.5 text-[12px] text-slate-500 dark:text-slate-400">
            Detayları görmek için tıkla →
          </p>
        </div>
      </button>
    ),

    top_parts: (
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-4 text-overline text-slate-500 dark:text-slate-400">
          En Çok Talep Edilen Parçalar
        </h3>
        {topParts && topParts.length > 0 ? (
          <SafeChart height={350} minHeight={250}>
            <BarChart data={topParts} margin={{ top: 20, right: 10, left: 10, bottom: 60 }}>
              <defs>
                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#E53935" stopOpacity={1} />
                  <stop offset="100%" stopColor="#B71C1C" stopOpacity={0.85} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis
                dataKey="honeywell_code"
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                angle={-45}
                textAnchor="end"
                height={70}
                interval={0}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                allowDecimals={false}
                tickFormatter={(v: number) => String(Math.round(v))}
              />
              <Tooltip
                formatter={(v) => [Math.round(Number(v ?? 0)), 'Talep']}
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 12,
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 8px 24px rgba(15,23,42,0.08)',
                }}
              />
              <Bar
                dataKey="request_count"
                fill="url(#barGrad)"
                radius={[6, 6, 0, 0]}
                barSize={36}
                label={{ position: 'top', fontSize: 10, fill: '#94a3b8' }}
              />
            </BarChart>
          </SafeChart>
        ) : (
          <EmptyState
            variant="compact"
            icon={<FileText size={18} />}
            title="Henüz veri yok"
            description="Talep verisi geldikçe burada en çok istenen parçalar listelenecek."
          />
        )}
      </div>
    ),

    trends: (
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-4 text-overline text-slate-500 dark:text-slate-400">
          Aylık Teklif & Gelir Trendi
        </h3>
        {trend && trend.length > 0 ? (
          <SafeChart height={300} minHeight={240}>
            <AreaChart
              data={trend.map((t) => ({
                ...t,
                label: `${t.year}-${String(t.month).padStart(2, '0')}`,
              }))}
            >
              <defs>
                <linearGradient id="gradRed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#E53935" stopOpacity={0.22} />
                  <stop offset="95%" stopColor="#E53935" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradBlue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1976D2" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#1976D2" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 12,
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 8px 24px rgba(15,23,42,0.08)',
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="quote_count"
                stroke="#E53935"
                fill="url(#gradRed)"
                name="Teklif"
                strokeWidth={2.5}
                dot={{ r: 4, fill: '#E53935' }}
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="revenue"
                stroke="#1976D2"
                fill="url(#gradBlue)"
                name="Gelir"
                strokeWidth={2.5}
                dot={{ r: 4, fill: '#1976D2' }}
              />
            </AreaChart>
          </SafeChart>
        ) : (
          <EmptyState
            variant="compact"
            icon={<FileText size={18} />}
            title="Henüz veri yok"
            description="Aylık teklif ve gelir trendleri burada görünecek."
          />
        )}
      </div>
    ),

    mrr_overview: (
      <button
        type="button"
        className="group flex w-full flex-col rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-800 dark:bg-slate-900"
        onClick={() => navigate('/subscriptions')}
      >
        <h3 className="mb-4 text-overline text-slate-500 dark:text-slate-400">
          Tekrarlayan Gelir (MRR)
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-overline text-slate-400 dark:text-slate-500">Toplam MRR</p>
            <p className="mt-1.5 text-[20px] font-bold leading-none tabular-nums text-slate-900 dark:text-white">
              {formatCurrency(mrrDashboard?.total_mrr ?? 0, 'TRY')}
            </p>
          </div>
          <div>
            <p className="text-overline text-slate-400 dark:text-slate-500">Aktif Abonelik</p>
            <p className="mt-1.5 text-[20px] font-bold leading-none tabular-nums text-slate-900 dark:text-white">
              {mrrDashboard?.active_count ?? 0}
            </p>
          </div>
          <div>
            <p className="text-overline text-slate-400 dark:text-slate-500">Kayıp (30g)</p>
            <p
              className={[
                'mt-1.5 text-[20px] font-bold leading-none tabular-nums',
                (mrrDashboard?.churn_count ?? 0) > 0
                  ? 'text-red-600'
                  : 'text-slate-900 dark:text-white',
              ].join(' ')}
            >
              {mrrDashboard?.churn_count ?? 0}
            </p>
          </div>
        </div>
      </button>
    ),

    activity_feed: (
      <div className="rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <h3 className="px-5 pb-3 pt-5 text-overline text-slate-500 dark:text-slate-400">
          Aktivite Akışı
        </h3>
        {activityFeed && activityFeed.length > 0 ? (
          <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
            {activityFeed.map((item) => {
              const Icon =
                item.activity_type === 'call'
                  ? Phone
                  : item.activity_type === 'meeting'
                    ? Handshake
                    : item.activity_type === 'email' || item.activity_type === 'email_received'
                      ? Mail
                      : item.activity_type === 'note'
                        ? FileText
                        : Zap;
              return (
                <li key={item.id} className="flex items-start gap-3 px-5 py-3">
                  <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                    <Icon size={14} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] text-slate-800 dark:text-slate-200">
                      {item.summary}
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
                      <span className="capitalize">{item.entity_type}</span>
                      <span className="mx-1.5">·</span>
                      <span className="tabular-nums">
                        {item.created_at ? formatRelativeTime(item.created_at) : ''}
                      </span>
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="px-5 pb-5">
            <EmptyState
              variant="compact"
              icon={<Zap size={18} />}
              title="Henüz aktivite yok"
              description="Çağrı, toplantı, e-posta ve notlar burada akacak."
            />
          </div>
        )}
      </div>
    ),

    action_required: (
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-4 text-overline text-slate-500 dark:text-slate-400">İşlem Bekleyen</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <button
            type="button"
            className="group flex items-start gap-3 rounded-xl border border-amber-100 bg-amber-50/60 p-4 text-left transition-all hover:border-amber-200 hover:bg-amber-50 focus:outline-none focus:ring-[3px] focus:ring-amber-200 dark:border-amber-900/40 dark:bg-amber-950/20"
            onClick={() => navigate('/emails?review=pending_review')}
          >
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
              <FileWarning size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-overline text-amber-700 dark:text-amber-400">İnceleme Bekleyen</p>
              <p className="mt-1 text-[24px] font-bold leading-none tabular-nums text-amber-900 dark:text-amber-200">
                {s.pending_review_count}
              </p>
              <p className="mt-1 text-[12px] text-amber-700/80 dark:text-amber-400/70">
                AI ile parse edilmiş, onay bekliyor
              </p>
            </div>
          </button>
          <button
            type="button"
            className="group flex items-start gap-3 rounded-xl border border-honeywell-red/15 bg-honeywell-red/4 p-4 text-left transition-all hover:border-honeywell-red/25 hover:bg-honeywell-red/8 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20"
            onClick={() => navigate('/quotes?status=draft')}
          >
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
              <AlertCircle size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-overline text-honeywell-red">Bekleyen Teklif Değeri</p>
              <p className="mt-1 text-[24px] font-bold leading-none tabular-nums text-slate-900 dark:text-white">
                {formatCurrency(s.pending_value, 'TRY')}
              </p>
              <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
                Taslak teklifler — gönderim/iyileştirme sırada
              </p>
            </div>
          </button>
        </div>
      </div>
    ),
  };

  /* ── Onboarding step config (kept inline for clarity; only 3 steps) ── */
  const onboardingSteps = [
    {
      done: Boolean(user?.email_setup_completed),
      label: 'E-posta yapılandırmasını tamamlayın',
      onClick: () => {
        if (!user?.email_setup_completed) setShowEmailSetup(true);
      },
    },
    {
      done: s.total_customers > 0,
      label: 'İlk müşterinizi ekleyin',
      onClick: () => navigate('/customers'),
    },
    {
      done: s.total_quotes > 0,
      label: 'İlk teklifinizi oluşturun',
      onClick: () => navigate('/quotes/new'),
    },
  ];
  const onboardingVisible = Boolean(
    user && (!user.email_setup_completed || s.total_customers === 0 || s.total_quotes === 0),
  );

  return (
    <div>
      <PageHeader
        title="Kontrol Paneli"
        description="Boru hattı, müşteri sağlığı ve ekip performansı tek panelde."
      />

      {/* ── Email setup popup (first login) ── */}
      <EmailSetupModal isOpen={showEmailSetup} onClose={() => setShowEmailSetup(false)} />

      <div className="space-y-6">
        {/* ── Onboarding Guide — brand-tinted, soft. Only shows while user is
            still setting up; disappears once all 3 steps are done. ── */}
        {onboardingVisible && (
          <div className="overflow-hidden rounded-2xl border border-honeywell-red/15 bg-linear-to-br from-honeywell-red/4 to-transparent p-5 shadow-(--shadow-xs)">
            <div className="flex items-start gap-3">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                <Sparkles size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">
                  Başlangıç Rehberi
                </h3>
                <p className="text-[12px] text-slate-500 dark:text-slate-400">
                  Hesabınızı tam çalışır hale getirmek için kalan adımlar.
                </p>
                <ul className="mt-4 space-y-2">
                  {onboardingSteps.map((step, idx) => (
                    <li key={idx} className="flex items-center gap-3">
                      <span
                        className={[
                          'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ring-1 ring-inset',
                          step.done
                            ? 'bg-emerald-50 text-emerald-700 ring-emerald-100'
                            : 'bg-white text-slate-500 ring-slate-200',
                        ].join(' ')}
                      >
                        {step.done ? <CheckCircle2 size={14} /> : idx + 1}
                      </span>
                      <button
                        type="button"
                        onClick={step.onClick}
                        className={[
                          'text-[13px] transition-colors',
                          step.done
                            ? 'text-slate-400 line-through'
                            : 'text-slate-700 hover:text-honeywell-red dark:text-slate-200',
                        ].join(' ')}
                      >
                        {step.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* ── KPI Cards ── */}
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onKpiDrag}>
          <SortableContext items={kpiOrder} strategy={rectSortingStrategy}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {kpiOrder.map((id) => (
                <SortableItem key={id} id={id}>
                  {kpiMap[id]}
                </SortableItem>
              ))}
            </div>
          </SortableContext>
        </DndContext>

        {/* ── Sections ── */}
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onSecDrag}>
          <SortableContext items={secOrder} strategy={rectSortingStrategy}>
            <div className="space-y-6">
              {secOrder.map((id) => (
                <SortableItem key={id} id={id}>
                  {secMap[id]}
                </SortableItem>
              ))}
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}
