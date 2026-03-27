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
  LineChart,
  Line,
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
const DEFAULT_SECTIONS = ['doughnuts', 'top_parts', 'trends', 'action_required'];

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
  const kpiMap: Record<string, ReactNode> = {
    total_emails: <KpiCard label="Toplam Mail" value={stats.total_emails} onClick={() => navigate('/emails')} />,
    total_quotes: <KpiCard label="Toplam Teklif" value={stats.total_quotes} onClick={() => navigate('/quotes')} />,
    total_parts: <KpiCard label="Toplam Parca" value={stats.total_parts} onClick={() => navigate('/parts')} />,
    total_customers: <KpiCard label="Toplam Musteri" value={stats.total_customers} onClick={() => navigate('/customers')} />,
    conversion_rate: <KpiCard label="Donusum Orani" value={`%${stats.conversion_rate}`} />,
    pending_review: <KpiCard label="Inceleme Bekleyen" value={stats.pending_review_count} onClick={() => navigate('/emails?review=pending_review')} />,
  };

  /* ── section map ── */
  const secMap: Record<string, ReactNode> = {
    doughnuts: (() => {
      const doughnutMap: Record<string, ReactNode> = {
        d_mail: <DoughnutChart title="Cevaplanan Mail Orani" filled={stats.answered_emails} total={stats.total_emails} colorIndex={0} />,
        d_value: <DoughnutChart title="Cevaplanan Parca Degeri" filled={stats.answered_parts_value} total={stats.total_parts_value} unit="USD" colorIndex={1} />,
        d_count: <DoughnutChart title="Cevaplanan Parca Sayisi" filled={stats.answered_parts_count} total={stats.total_parts_count} unit="adet" colorIndex={2} />,
        d_quote: <DoughnutChart title="Onaylanan Teklif Orani" filled={stats.approved_quotes} total={stats.total_quotes} colorIndex={3} />,
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

    top_parts: (
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
          En Cok Talep Edilen Parcalar
        </h3>
        {topParts && topParts.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={topParts} margin={{ top: 10, right: 10, left: 10, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="honeywell_code"
                tick={{ fontSize: 10, fill: '#666' }}
                angle={-45}
                textAnchor="end"
                height={70}
                interval={0}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                allowDecimals={false}
                tickFormatter={(v: number) => String(Math.round(v))}
              />
              <Tooltip
                formatter={(v: any) => [Math.round(v), 'Talep']}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Bar dataKey="request_count" fill="#D32F2F" radius={[4, 4, 0, 0]} barSize={32} />
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
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="quote_count" stroke="#D32F2F" name="Teklif" strokeWidth={2} />
              <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="#1976D2" name="Gelir" strokeWidth={2} />
            </LineChart>
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
            <p className="mt-1 text-2xl font-bold text-amber-800">{stats.pending_review_count}</p>
          </div>
          <div
            className="cursor-pointer rounded-lg border-l-4 border-l-honeywell-red bg-red-50 p-4 hover:bg-red-100 transition-colors"
            onClick={() => navigate('/quotes?status=draft')}
          >
            <p className="text-sm font-medium text-red-900">Bekleyen Teklif Degeri</p>
            <p className="mt-1 text-2xl font-bold text-red-800">{formatCurrency(stats.pending_value, 'TRY')}</p>
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
