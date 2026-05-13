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
import { Printer, FileText, AlertCircle } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { analyticsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import type { TopPart, TrendData } from '../../lib/types';

interface PeriodOption {
  label: string;
  days: number;
  months: number;
}

// Round-10 R10-FE-13 — `as const` lets noUncheckedIndexedAccess narrow
// PERIOD_OPTIONS[0] to the first literal entry (non-undefined) instead
// of `PeriodOption | undefined`.
const PERIOD_OPTIONS = [
  { label: 'Son 30 Gün', days: 30, months: 1 },
  { label: 'Son 90 Gün', days: 90, months: 3 },
  { label: 'Son 6 Ay', days: 180, months: 6 },
  { label: 'Son 1 Yıl', days: 365, months: 12 },
] as const satisfies readonly PeriodOption[];

const TOP_PARTS_LIMIT = 20;

interface CategoryItem {
  category: string;
  item_count: number;
  total_quantity: number;
  total_value: number;
}

interface NoPricePart {
  id: number | null;
  honeywell_code: string;
  name_en: string | null;
  name_tr: string | null;
  category: string | null;
  status: string;
}

const TOOLTIP_STYLE = {
  fontSize: 12,
  borderRadius: 12,
  border: '1px solid #e2e8f0',
  boxShadow: '0 8px 24px rgba(15,23,42,0.08)',
};

/**
 * SectionCard — wrapper that gives every report block the same shell.
 * Title sits on a slate-tinted header strip; body is plain so charts/tables
 * can use the full width without nested padding.
 */
function SectionCard({
  title,
  children,
  className = '',
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900 ${className}`}
    >
      <div className="border-b border-slate-100 px-5 py-3.5 dark:border-slate-800">
        <h3 className="text-overline text-slate-500 dark:text-slate-400">{title}</h3>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

export default function ReportsPage() {
  const t = useT();
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodOption>(PERIOD_OPTIONS[0]);

  const { data: trendData, isLoading: isTrendLoading } = useQuery<TrendData[]>({
    queryKey: ['reports-monthly-trend', selectedPeriod.months],
    queryFn: () => analyticsApi.getMonthlyTrend(selectedPeriod.months),
  });

  const { data: categoryData, isLoading: isCategoryLoading } = useQuery<CategoryItem[]>({
    queryKey: ['reports-category-breakdown', selectedPeriod.days],
    queryFn: async () => {
      const raw = await analyticsApi.getCategoryBreakdown(selectedPeriod.days);
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
      return (raw as unknown as { items: NoPricePart[] }).items ?? [];
    },
  });

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
    <div className="print:space-y-4">
      <PageHeader title="Raporlar" description="Satış raporları ve dönemsel kırılımlar">
        {/* Period selector — segmented control */}
        <div className="hidden rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 sm:inline-flex sm:gap-1 dark:border-slate-800 dark:bg-slate-900/40 print:hidden">
          {PERIOD_OPTIONS.map((option) => {
            const isActive = selectedPeriod.days === option.days;
            return (
              <button
                key={option.days}
                type="button"
                onClick={() => setSelectedPeriod(option)}
                className={[
                  'inline-flex h-8 items-center rounded-[10px] px-3 text-[12px] font-medium transition-all',
                  'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                  isActive
                    ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
                    : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
                ].join(' ')}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        <Button variant="secondary" onClick={handlePrint} className="print:hidden">
          <Printer size={14} />
          PDF İndir
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Section 1: Monthly Trend */}
        <SectionCard title="Aylık Teklif & Gelir Trendi">
          {isTrendLoading ? (
            <div className="flex h-[300px] items-center justify-center">
              <p className="text-[13px] text-slate-400">{t('common.loading')}</p>
            </div>
          ) : trendChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={trendChartData}>
                <defs>
                  <linearGradient id="rptGradRed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#E53935" stopOpacity={0.22} />
                    <stop offset="95%" stopColor="#E53935" stopOpacity={0} />
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
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="quote_count"
                  stroke="#E53935"
                  fill="url(#rptGradRed)"
                  name="Teklif Sayısı"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#E53935' }}
                />
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="revenue"
                  stroke="#1976D2"
                  fill="url(#rptGradBlue)"
                  name="Gelir"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#1976D2' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState variant="compact" icon={<FileText size={18} />} title="Henüz veri yok" />
          )}
        </SectionCard>

        {/* Section 2: Category Breakdown */}
        <SectionCard title="Kategori Dağılımı">
          {isCategoryLoading ? (
            <div className="flex h-[300px] items-center justify-center">
              <p className="text-[13px] text-slate-400">{t('common.loading')}</p>
            </div>
          ) : categoryData && categoryData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={categoryData}>
                <defs>
                  <linearGradient id="catBarGradRed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#E53935" stopOpacity={1} />
                    <stop offset="100%" stopColor="#B71C1C" stopOpacity={0.85} />
                  </linearGradient>
                  <linearGradient id="catBarGradBlue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1976D2" stopOpacity={1} />
                    <stop offset="100%" stopColor="#0D47A1" stopOpacity={0.85} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="category"
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  interval={0}
                  angle={-15}
                  textAnchor="end"
                  height={60}
                />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar
                  yAxisId="left"
                  dataKey="item_count"
                  fill="url(#catBarGradRed)"
                  name="Kalem Sayısı"
                  radius={[6, 6, 0, 0]}
                />
                <Bar
                  yAxisId="right"
                  dataKey="total_value"
                  fill="url(#catBarGradBlue)"
                  name="Toplam Değer (USD)"
                  radius={[6, 6, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState variant="compact" icon={<FileText size={18} />} title="Henüz veri yok" />
          )}
        </SectionCard>

        {/* Section 3: Top Requested Parts */}
        <div className="print-page-break" />
        <SectionCard title="En Çok Talep Edilen Parçalar">
          {isTopPartsLoading ? (
            <p className="py-8 text-center text-[13px] text-slate-400">{t('common.loading')}</p>
          ) : topParts && topParts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800">
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      #
                    </th>
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      Honeywell Kodu
                    </th>
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      Parça Adı
                    </th>
                    <th className="px-3 py-2.5 text-right text-overline text-slate-500 dark:text-slate-400">
                      Talep
                    </th>
                    <th className="px-3 py-2.5 text-right text-overline text-slate-500 dark:text-slate-400">
                      Toplam Miktar
                    </th>
                    <th className="px-3 py-2.5 text-right text-overline text-slate-500 dark:text-slate-400">
                      Toplam Değer
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {topParts.map((part: TopPart, index: number) => (
                    <tr
                      key={part.honeywell_code}
                      className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-3 py-2.5 text-[12px] tabular-nums text-slate-400">
                        {index + 1}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
                        {part.honeywell_code}
                      </td>
                      <td className="px-3 py-2.5 text-[13px] text-slate-700 dark:text-slate-200">
                        {part.name_tr || part.name_en || part.name || '—'}
                      </td>
                      <td className="px-3 py-2.5 text-right text-[13px] tabular-nums text-slate-900 dark:text-white">
                        {part.request_count}
                      </td>
                      <td className="px-3 py-2.5 text-right text-[13px] tabular-nums text-slate-700 dark:text-slate-200">
                        {part.total_quantity}
                      </td>
                      <td className="px-3 py-2.5 text-right text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                        {part.total_value != null ? formatCurrency(part.total_value) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState variant="compact" icon={<FileText size={18} />} title="Henüz veri yok" />
          )}
        </SectionCard>

        {/* Section 4: Parts Without Price */}
        <SectionCard title="Fiyatsız Parçalar">
          {isNoPriceLoading ? (
            <p className="py-8 text-center text-[13px] text-slate-400">{t('common.loading')}</p>
          ) : noPriceParts && noPriceParts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800">
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      Honeywell Kodu
                    </th>
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      Parça Adı
                    </th>
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      Kategori
                    </th>
                    <th className="px-3 py-2.5 text-overline text-slate-500 dark:text-slate-400">
                      Durum
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {noPriceParts.map((part, index) => (
                    <tr
                      key={part.honeywell_code + '-' + index}
                      className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-3 py-2.5 font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
                        {part.honeywell_code}
                      </td>
                      <td className="px-3 py-2.5 text-[13px] text-slate-700 dark:text-slate-200">
                        {part.name_tr || part.name_en || '—'}
                      </td>
                      <td className="px-3 py-2.5 text-[12px] text-slate-500 dark:text-slate-400">
                        {part.category || '—'}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge
                          variant={part.status === 'unknown_part' ? 'danger' : 'warning'}
                          size="sm"
                          dot
                        >
                          {part.status === 'unknown_part' ? 'Bilinmeyen Parça' : 'Fiyat Yok'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-3 flex items-center gap-2 text-[12px] text-slate-500 dark:text-slate-400">
                <AlertCircle size={12} className="text-amber-500" />
                Toplam {noPriceParts.length} parça fiyat bilgisi eksik
              </div>
            </div>
          ) : (
            <EmptyState
              variant="compact"
              icon={<FileText size={18} />}
              title="Tüm parçaların fiyat bilgisi mevcut"
            />
          )}
        </SectionCard>
      </div>
    </div>
  );
}
