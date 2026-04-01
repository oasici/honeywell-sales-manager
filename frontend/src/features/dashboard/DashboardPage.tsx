import { useState, useCallback, useEffect, type ReactNode } from 'react';
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
import {
  SortableContext,
  rectSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Skeleton } from '../../components/ui/Skeleton';
import { dashboardApi, analyticsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { DashboardStats, TopPart, TrendData } from '../../lib/types';
import { AtRiskCustomersCard } from './AtRiskCustomersCard';
import { KpiCard } from './KpiCard';
import { DoughnutChart } from './DoughnutChart';
import { SortableItem } from './SortableItem';

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
const DEFAULT_SECTIONS = ['doughnuts', 'at_risk_customers', 'top_parts', 'trends', 'action_required'];

/* ─────────────────── MAIN ─────────────────── */
export default function DashboardPage() {
  const navigate = useNavigate();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const [kpiOrder, setKpiOrder] = useState(() => loadOrder('dash-kpi', DEFAULT_KPI));
  const [doughnutOrder, setDoughnutOrder] = useState(() => loadOrder('dash-donut', DEFAULT_DOUGHNUTS));
  const [secOrder, setSecOrder] = useState(() => loadOrder('dash-sec', DEFAULT_SECTIONS));

  /* ── Email setup popup (first login only) ── */
  const user = useAuthStore((s) => s.user);
  const [showEmailSetup, setShowEmailSetup] = useState(false);

  useEffect(() => {
    if (user && !user.email_setup_completed) {
      setShowEmailSetup(true);
    }
  }, [user]);

  /* ── data ── */
  const { data: stats, isLoading } = useQuery<DashboardStats>({
    queryKey: ['dashboard-stats'],
    queryFn: dashboardApi.getStats,
  });
  const { data: topParts } = useQuery<TopPart[]>({
    queryKey: ['top-parts'],
    queryFn: () => analyticsApi.getTopParts(30, 10),
  });
  const { data: trend } = useQuery<TrendData[]>({
    queryKey: ['monthly-trend'],
    queryFn: () => analyticsApi.getMonthlyTrend(6),
  });

  /* ── drag handlers ── */
  const onKpiDrag = useCallback((e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setKpiOrder((prev) => {
      const next = arrayMove(prev, prev.indexOf(active.id as string), prev.indexOf(over.id as string));
      localStorage.setItem('dash-kpi', JSON.stringify(next));
      return next;
    });
  }, []);

  const onDoughnutDrag = useCallback((e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setDoughnutOrder((prev) => {
      const next = arrayMove(prev, prev.indexOf(active.id as string), prev.indexOf(over.id as string));
      localStorage.setItem('dash-donut', JSON.stringify(next));
      return next;
    });
  }, []);

  const onSecDrag = useCallback((e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setSecOrder((prev) => {
      const next = arrayMove(prev, prev.indexOf(active.id as string), prev.indexOf(over.id as string));
      localStorage.setItem('dash-sec', JSON.stringify(next));
      return next;
    });
  }, []);

  /* ── loading ── */
  if (isLoading || !stats) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Kontrol Paneli</h1>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-56 rounded-xl" />)}
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
    total_emails: <KpiCard label="Toplam Mail" value={s.total_emails} onClick={() => navigate('/emails')} />,
    total_quotes: <KpiCard label="Toplam Teklif" value={s.total_quotes} onClick={() => navigate('/quotes')} />,
    total_parts: <KpiCard label="Toplam Parca" value={s.total_parts} onClick={() => navigate('/parts')} />,
    total_customers: <KpiCard label="Toplam Musteri" value={s.total_customers} onClick={() => navigate('/customers')} />,
    conversion_rate: <KpiCard label="Donusum Orani" value={`%${s.conversion_rate}`} />,
    pending_review: <KpiCard label="Inceleme Bekleyen" value={s.pending_review_count} onClick={() => navigate('/emails?review=pending_review')} />,
  };

  /* ── section map ── */
  const secMap: Record<string, ReactNode> = {
    doughnuts: (() => {
      const doughnutMap: Record<string, ReactNode> = {
        d_mail: <DoughnutChart title="Cevaplanan Mail Orani" filled={s.answered_emails} total={s.total_emails} colorIndex={0} />,
        d_value: <DoughnutChart title="Cevaplanan Parca Degeri" filled={s.answered_parts_value} total={s.total_parts_value} unit="USD" colorIndex={1} />,
        d_count: <DoughnutChart title="Cevaplanan Parca Sayisi" filled={s.answered_parts_count} total={s.total_parts_count} unit="adet" colorIndex={2} />,
        d_quote: <DoughnutChart title="Onaylanan Teklif Orani" filled={s.approved_quotes} total={s.total_quotes} colorIndex={3} />,
      };
      return (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Performans Metrikleri
          </h3>
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDoughnutDrag}>
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

    top_parts: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          En Cok Talep Edilen Parcalar
        </h3>
        {topParts && topParts.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
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
                formatter={(v: any) => [Math.round(v), 'Talep']}
                contentStyle={{ fontSize: 12, borderRadius: 12, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
              />
              <Bar dataKey="request_count" fill="url(#barGrad)" radius={[6, 6, 0, 0]} barSize={36} label={{ position: 'top', fontSize: 10, fill: '#94a3b8' }} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Henuz veri yok</p>
        )}
      </div>
    ),

    trends: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Aylik Teklif & Gelir Trendi
        </h3>
        {trend && trend.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trend.map((t) => ({ ...t, label: `${t.year}-${String(t.month).padStart(2, '0')}` }))}>
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
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
              <Legend />
              <Area yAxisId="left" type="monotone" dataKey="quote_count" stroke="#D32F2F" fill="url(#gradRed)" name="Teklif" strokeWidth={2.5} dot={{ r: 4, fill: '#D32F2F' }} />
              <Area yAxisId="right" type="monotone" dataKey="revenue" stroke="#1976D2" fill="url(#gradBlue)" name="Gelir" strokeWidth={2.5} dot={{ r: 4, fill: '#1976D2' }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Henuz veri yok</p>
        )}
      </div>
    ),

    action_required: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          Islem Bekleyen
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div
            className="cursor-pointer rounded-lg border-l-4 border-l-amber-500 bg-amber-50 p-4 hover:bg-amber-100 transition-colors"
            onClick={() => navigate('/emails?review=pending_review')}
          >
            <p className="text-sm font-medium text-amber-900">Inceleme Bekleyen Mailler</p>
            <p className="mt-1 text-2xl font-bold text-amber-800">{s.pending_review_count}</p>
          </div>
          <div
            className="cursor-pointer rounded-lg border-l-4 border-l-honeywell-red bg-red-50 p-4 hover:bg-red-100 transition-colors"
            onClick={() => navigate('/quotes?status=draft')}
          >
            <p className="text-sm font-medium text-red-900">Bekleyen Teklif Degeri</p>
            <p className="mt-1 text-2xl font-bold text-red-800">{formatCurrency(s.pending_value, 'TRY')}</p>
          </div>
        </div>
      </div>
    ),
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Kontrol Paneli</h1>

      {/* ── Email setup popup (first login) ── */}
      <EmailSetupModal
        isOpen={showEmailSetup}
        onClose={() => setShowEmailSetup(false)}
      />

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
