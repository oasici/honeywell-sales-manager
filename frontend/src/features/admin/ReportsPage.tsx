import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Printer } from 'lucide-react';

import { Card } from '../../components/ui/Card';
import { analyticsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { TopPart, TrendData } from '../../lib/types';

/* ── Period options ───────────────────────────────────── */
interface PeriodOption {
  label: string;
  days: number;
  months: number;
}

const PERIOD_OPTIONS: PeriodOption[] = [
  { label: 'Son 30 Gun', days: 30, months: 1 },
  { label: 'Son 90 Gun', days: 90, months: 3 },
  { label: 'Son 6 Ay', days: 180, months: 6 },
  { label: 'Son 1 Yil', days: 365, months: 12 },
];

const TOP_PARTS_LIMIT = 20;

/* ── Category breakdown item type ────────────────────── */
interface CategoryItem {
  category: string;
  item_count: number;
  total_quantity: number;
  total_value: number;
}

/* ── Parts without price item type ───────────────────── */
interface NoPricePart {
  id: number | null;
  honeywell_code: string;
  name_en: string | null;
  name_tr: string | null;
  category: string | null;
  status: string;
}

/* ── Main component ──────────────────────────────────── */
export default function ReportsPage() {
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption>(PERIOD_OPTIONS[0]);

  /* ── Queries ── */
  const { data: trendData, isLoading: isTrendLoading } = useQuery<TrendData[]>({
    queryKey: ['reports-monthly-trend', selectedPeriod.months],
    queryFn: () => analyticsApi.getMonthlyTrend(selectedPeriod.months),
  });

  const { data: categoryData, isLoading: isCategoryLoading } = useQuery<CategoryItem[]>({
    queryKey: ['reports-category-breakdown', selectedPeriod.days],
    queryFn: async () => {
      const raw = await analyticsApi.getCategoryBreakdown(selectedPeriod.days);
      // API may return Record<string, number> or array depending on backend version
      if (Array.isArray(raw)) return raw;
      return Object.entries(raw).map(([category, count]) => ({
        category,
        item_count: count as number,
        total_quantity: 0,
        total_value: 0,
      }));
    },
  });

  const { data: topParts, isLoading: isTopPartsLoading } = useQuery<TopPart[]>({
    queryKey: ['reports-top-parts', selectedPeriod.days],
    queryFn: () => analyticsApi.getTopParts(selectedPeriod.days, TOP_PARTS_LIMIT),
  });

  const { data: noPriceParts, isLoading: isNoPriceLoading } = useQuery<NoPricePart[]>({
    queryKey: ['reports-parts-without-price'],
    queryFn: async (): Promise<NoPricePart[]> => {
      const raw = await analyticsApi.getPartsWithoutPrice();
      if (Array.isArray(raw)) return raw as unknown as NoPricePart[];
      return ((raw as unknown as { items: NoPricePart[] }).items) ?? [];
    },
  });

  /* ── Derived chart data ── */
  const trendChartData = useMemo(() => {
    if (!trendData) return [];
    return trendData.map((t) => ({
      ...t,
      label: `${t.year}-${String(t.month).padStart(2, '0')}`,
    }));
  }, [trendData]);

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="space-y-6 print:space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Raporlar</h1>
          <p className="text-sm text-gray-500">Satis Raporlari</p>
        </div>

        <div className="flex items-center gap-3 print:hidden">
          {/* Period selector */}
          <div className="flex rounded-lg border border-gray-200 bg-white shadow-sm">
            {PERIOD_OPTIONS.map((option) => (
              <button
                key={option.days}
                onClick={() => setSelectedPeriod(option)}
                className={`px-3 py-2 text-sm font-medium transition-colors first:rounded-l-lg last:rounded-r-lg ${
                  selectedPeriod.days === option.days
                    ? 'bg-honeywell-red text-white'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          {/* PDF / Print button */}
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800"
          >
            <Printer size={16} />
            PDF Rapor Indir
          </button>
        </div>
      </div>

      {/* Section 1: Monthly Trend */}
      <Card title="Aylik Teklif & Gelir Trendi">
        {isTrendLoading ? (
          <div className="flex h-[300px] items-center justify-center">
            <p className="text-sm text-gray-400">Yukleniyor...</p>
          </div>
        ) : trendChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trendChartData}>
              <defs>
                <linearGradient id="rptGradRed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#D32F2F" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#D32F2F" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="rptGradBlue" x1="0" y1="0" x2="0" y2="1">
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
              <Area yAxisId="left" type="monotone" dataKey="quote_count" stroke="#D32F2F" fill="url(#rptGradRed)" name="Teklif Sayisi" strokeWidth={2.5} dot={{ r: 4, fill: '#D32F2F' }} />
              <Area yAxisId="right" type="monotone" dataKey="revenue" stroke="#1976D2" fill="url(#rptGradBlue)" name="Gelir" strokeWidth={2.5} dot={{ r: 4, fill: '#1976D2' }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Henuz veri yok</p>
        )}
      </Card>

      {/* Section 2: Category Breakdown */}
      <Card title="Kategori Dagilimi">
        {isCategoryLoading ? (
          <div className="flex h-[300px] items-center justify-center">
            <p className="text-sm text-gray-400">Yukleniyor...</p>
          </div>
        ) : categoryData && categoryData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={categoryData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="category"
                tick={{ fontSize: 10 }}
                interval={0}
                angle={-15}
                textAnchor="end"
                height={60}
              />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
              <Legend />
              <Bar
                yAxisId="left"
                dataKey="item_count"
                fill="#D32F2F"
                name="Kalem Sayisi"
                radius={[6, 6, 0, 0]}
              />
              <Bar
                yAxisId="right"
                dataKey="total_value"
                fill="#1976D2"
                name="Toplam Deger (USD)"
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Henuz veri yok</p>
        )}
      </Card>

      {/* Section 3: Top Requested Parts */}
      <div className="print-page-break" />
      <Card title="En Cok Talep Edilen Parcalar">
        {isTopPartsLoading ? (
          <p className="py-8 text-center text-sm text-gray-400">Yukleniyor...</p>
        ) : topParts && topParts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <th className="px-3 py-3">#</th>
                  <th className="px-3 py-3">Honeywell Kodu</th>
                  <th className="px-3 py-3">Parca Adi</th>
                  <th className="px-3 py-3 text-right">Talep Sayisi</th>
                  <th className="px-3 py-3 text-right">Toplam Miktar</th>
                  <th className="px-3 py-3 text-right">Toplam Deger</th>
                </tr>
              </thead>
              <tbody>
                {topParts.map((part: any, index: number) => (
                  <tr
                    key={part.honeywell_code}
                    className="border-b border-gray-100 transition-colors hover:bg-gray-50"
                  >
                    <td className="px-3 py-3 text-gray-400">{index + 1}</td>
                    <td className="px-3 py-3 font-mono text-xs font-medium">
                      {part.honeywell_code}
                    </td>
                    <td className="px-3 py-3">
                      {part.name_tr || part.name_en || part.name || '-'}
                    </td>
                    <td className="px-3 py-3 text-right">{part.request_count}</td>
                    <td className="px-3 py-3 text-right">{part.total_quantity}</td>
                    <td className="px-3 py-3 text-right">
                      {part.total_value != null
                        ? formatCurrency(part.total_value)
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Henuz veri yok</p>
        )}
      </Card>

      {/* Section 4: Parts Without Price */}
      <Card title="Fiyatsiz Parcalar">
        {isNoPriceLoading ? (
          <p className="py-8 text-center text-sm text-gray-400">Yukleniyor...</p>
        ) : noPriceParts && noPriceParts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <th className="px-3 py-3">Honeywell Kodu</th>
                  <th className="px-3 py-3">Parca Adi</th>
                  <th className="px-3 py-3">Kategori</th>
                  <th className="px-3 py-3">Durum</th>
                </tr>
              </thead>
              <tbody>
                {noPriceParts.map((part, index) => (
                  <tr
                    key={part.honeywell_code + '-' + index}
                    className="border-b border-gray-100 transition-colors hover:bg-gray-50"
                  >
                    <td className="px-3 py-3 font-mono text-xs font-medium">
                      {part.honeywell_code}
                    </td>
                    <td className="px-3 py-3">
                      {part.name_tr || part.name_en || '-'}
                    </td>
                    <td className="px-3 py-3">{part.category || '-'}</td>
                    <td className="px-3 py-3">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          part.status === 'unknown_part'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}
                      >
                        {part.status === 'unknown_part'
                          ? 'Bilinmeyen Parca'
                          : 'Fiyat Yok'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-gray-400">
              Toplam {noPriceParts.length} parca fiyat bilgisi eksik
            </p>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">
            Tum parcalarin fiyat bilgisi mevcut
          </p>
        )}
      </Card>
    </div>
  );
}
