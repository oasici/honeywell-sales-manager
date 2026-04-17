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
import { dashboardApi, analyticsApi, subscriptionsApi, activitiesApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
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

/* ─────────────────── relative time helper ─────────────────── */
function formatRelativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 1) return 'az önce';
  if (diffMins < 60) return `${diffMins}d once`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}s once`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}g once`;
}

/* ─────────────────── localStorage helpers ─────────────────── */
function loadOrder(key: string, fallback: string[]): string[] {
  try {
    const s = localStorage.getItem(key);
    return s ? JSON.parse(s) : fallback;
  } catch {
    return fallback;
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
  const [secOrder, setSecOrder] = useState(() => loadOrder('dash-seç', DEFAULT_SECTIONS));

  /* ── Email setup popup (first login only) ── */
  const user = useAuthStore((s) => s.user);
  const [showEmailSetup, setShowEmailSetup] = useState(() =>
    Boolean(user && !user.email_setup_completed),
  );

  /* ── data ── */
  const { data: stats, isLoading } = useQuery<DashboardStats>({
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
      localStorage.setItem('dash-kpi', JSON.stringify(next));
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
      localStorage.setItem('dash-donut', JSON.stringify(next));
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
      localStorage.setItem('dash-seç', JSON.stringify(next));
      return next;
    });
  }, []);

  /* ── loading ── */
  if (isLoading || !stats) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Kontrol Paneli</h1>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-56 rounded-xl" />
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
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
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
      <div
        className="cursor-pointer rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-colors hover:border-honeywell-red/30"
        onClick={() => navigate('/admin/data-quality')}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter') navigate('/admin/data-quality');
        }}
      >
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Veri Kalitesi
        </h3>
        <div className="flex items-center gap-4">
          <div className="relative h-14 w-14">
            <svg viewBox="0 0 36 36" className="h-14 w-14 -rotate-90" aria-hidden="true">
              <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e5e7eb" strokeWidth="3" />
              <circle
                cx="18"
                cy="18"
                r="15.5"
                fill="none"
                stroke={
                  (dataQuality?.data?.avg_score ?? 0) >= 75
                    ? '#22c55e'
                    : (dataQuality?.data?.avg_score ?? 0) >= 50
                      ? '#eab308'
                      : '#ef4444'
                }
                strokeWidth="3"
                strokeDasharray={`${dataQuality?.data?.avg_score ?? 0} ${100 - (dataQuality?.data?.avg_score ?? 0)}`}
                strokeLinecap="round"
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-gray-900">
              {Math.round(dataQuality?.data?.avg_score ?? 0)}
            </span>
          </div>
          <p className="text-sm text-gray-500">Genel veri kalite puani</p>
        </div>
      </div>
    ),

    top_parts: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          En Çok Talep Edilen Parçalar
        </h3>
        {topParts && topParts.length > 0 ? (
          <SafeChart height={350} minHeight={250}>
            <BarChart data={topParts} margin={{ top: 20, right: 10, left: 10, bottom: 60 }}>
              <defs>
                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#D32F2F" stopOpacity={1} />
                  <stop offset="100%" stopColor="#B71C1C" stopOpacity={0.8} />
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
                  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
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
          <p className="py-8 text-center text-sm text-gray-400">Henüz veri yok</p>
        )}
      </div>
    ),

    trends: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Aylik Teklif & Gelir Trendi
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
                  <stop offset="5%" stopColor="#D32F2F" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#D32F2F" stopOpacity={0} />
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
                  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                }}
              />
              <Legend />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="quote_count"
                stroke="#D32F2F"
                fill="url(#gradRed)"
                name="Teklif"
                strokeWidth={2.5}
                dot={{ r: 4, fill: '#D32F2F' }}
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
          <p className="py-8 text-center text-sm text-gray-400">Henüz veri yok</p>
        )}
      </div>
    ),

    mrr_overview: (
      <div
        className="cursor-pointer rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-colors hover:border-honeywell-red/30"
        onClick={() => navigate('/subscriptions')}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter') navigate('/subscriptions');
        }}
      >
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Tekrarlayan Gelir (MRR)
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-gray-400">Toplam MRR</p>
            <p className="text-lg font-bold text-gray-900">
              {formatCurrency(mrrDashboard?.total_mrr ?? 0, 'TRY')}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Aktif Abonelik</p>
            <p className="text-lg font-bold text-gray-900">{mrrDashboard?.active_count ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Kayip (30g)</p>
            <p
              className={`text-lg font-bold ${(mrrDashboard?.churn_count ?? 0) > 0 ? 'text-red-600' : 'text-gray-900'}`}
            >
              {mrrDashboard?.churn_count ?? 0}
            </p>
          </div>
        </div>
      </div>
    ),

    activity_feed: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Aktivite Akisi
        </h3>
        {activityFeed && activityFeed.length > 0 ? (
          <ul className="max-h-80 overflow-y-auto space-y-2 pr-1">
            {activityFeed.map((item) => (
              <li key={item.id} className="flex items-start gap-3 py-1.5">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs">
                  {item.activity_type === 'call'
                    ? '📞'
                    : item.activity_type === 'meeting'
                      ? '🤝'
                      : item.activity_type === 'email' || item.activity_type === 'email_received'
                        ? '✉️'
                        : item.activity_type === 'note'
                          ? '📝'
                          : '⚡'}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-gray-800">{item.summary}</p>
                  <p className="text-xs text-gray-400">
                    {item.entity_type}
                    {' · '}
                    {item.created_at ? formatRelativeTime(item.created_at) : ''}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-6 text-center text-sm text-gray-400">Henüz aktivite yok</p>
        )}
      </div>
    ),

    action_required: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          İşlem Bekleyen
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div
            className="cursor-pointer rounded-lg border-l-4 border-l-amber-500 bg-amber-50 p-4 hover:bg-amber-100 transition-colors"
            onClick={() => navigate('/emails?review=pending_review')}
          >
            <p className="text-sm font-medium text-amber-900">İnceleme Bekleyen Mailler</p>
            <p className="mt-1 text-2xl font-bold text-amber-800">{s.pending_review_count}</p>
          </div>
          <div
            className="cursor-pointer rounded-lg border-l-4 border-l-honeywell-red bg-red-50 p-4 hover:bg-red-100 transition-colors"
            onClick={() => navigate('/quotes?status=draft')}
          >
            <p className="text-sm font-medium text-red-900">Bekleyen Teklif Degeri</p>
            <p className="mt-1 text-2xl font-bold text-red-800">
              {formatCurrency(s.pending_value, 'TRY')}
            </p>
          </div>
        </div>
      </div>
    ),
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Kontrol Paneli</h1>

      {/* ── Email setup popup (first login) ── */}
      <EmailSetupModal isOpen={showEmailSetup} onClose={() => setShowEmailSetup(false)} />

      {/* ── Onboarding Guide ── */}
      {user && (!user.email_setup_completed || s.total_customers === 0 || s.total_quotes === 0) && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 shadow-sm dark:border-blue-800 dark:bg-blue-900/20">
          <h3 className="mb-3 text-sm font-semibold text-blue-900 dark:text-blue-300">
            Baslangic Rehberi
          </h3>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${user.email_setup_completed ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-500'}`}
              >
                1
              </span>
              <button
                type="button"
                onClick={() => {
                  if (!user.email_setup_completed) setShowEmailSetup(true);
                }}
                className={`text-sm ${user.email_setup_completed ? 'text-green-700 line-through' : 'text-blue-700 hover:underline cursor-pointer'}`}
              >
                E-posta yapilandirmasini tamamlayin
              </button>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${s.total_customers > 0 ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-500'}`}
              >
                2
              </span>
              <button
                type="button"
                onClick={() => navigate('/customers')}
                className={`text-sm ${s.total_customers > 0 ? 'text-green-700 line-through' : 'text-blue-700 hover:underline cursor-pointer'}`}
              >
                İlk musterinizi ekleyin
              </button>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${s.total_quotes > 0 ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-500'}`}
              >
                3
              </span>
              <button
                type="button"
                onClick={() => navigate('/quotes/new')}
                className={`text-sm ${s.total_quotes > 0 ? 'text-green-700 line-through' : 'text-blue-700 hover:underline cursor-pointer'}`}
              >
                İlk teklifinizi olusturun
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── KPI Cards ── */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onKpiDrag}>
        <SortableContext items={kpiOrder} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
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
  );
}
