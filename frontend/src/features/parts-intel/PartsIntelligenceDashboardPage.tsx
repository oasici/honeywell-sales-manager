import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState } from '../../components/ui/EmptyState';
import { PageHeader } from '../../components/ui/PageHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { v10PartsIntelApi } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/formatters';

interface SummaryPayload {
  generated_at: string;
  tier_counts: { A: number; B: number; C: number };
  dead_stock_count: number;
  frozen_capital_total: number;
  heatmap_months_covered: number;
  total_active_parts: number;
}

interface DeadStockItem {
  spare_part_id: number;
  honeywell_code: string | null;
  name: string | null;
  supplier_price: number | null;
  frozen_capital_estimate: number;
  last_quoted_at: string | null;
}

interface ObsolescenceRow {
  spare_part_id: number;
  honeywell_code: string | null;
  name: string | null;
  risk_score: number;
  inactivity_days: number;
  missing_fields_count: number;
  price_age_days: number;
  quote_freq_decay_pct: number;
}

interface DataHealthEnvelope {
  generated_at: string;
  value: number;
  confidence: string;
  drivers: { label: string; impact: number; filled_pct?: number }[];
  recommended_actions: string[];
}

function riskTone(score: number): 'success' | 'warning' | 'danger' {
  if (score >= 70) return 'danger';
  if (score >= 40) return 'warning';
  return 'success';
}

function healthTone(score: number): 'success' | 'warning' | 'danger' {
  if (score >= 75) return 'success';
  if (score >= 50) return 'warning';
  return 'danger';
}

export default function PartsIntelligenceDashboardPage() {
  const summaryQuery = useQuery<SummaryPayload>({
    queryKey: ['v10', 'parts-intel', 'summary'],
    queryFn: () => v10PartsIntelApi.getSummary(),
    retry: false,
  });

  const deadStockQuery = useQuery<{
    items: DeadStockItem[];
    total: number;
    frozen_capital_total: number;
  }>({
    queryKey: ['v10', 'parts-intel', 'dead-stock'],
    queryFn: () => v10PartsIntelApi.getDeadStock(180, 20),
    retry: false,
  });

  const obsolescenceQuery = useQuery<{ items: ObsolescenceRow[]; total: number }>({
    queryKey: ['v10', 'parts-intel', 'obsolescence-watch'],
    queryFn: () => v10PartsIntelApi.getObsolescenceWatch(20),
    retry: false,
  });

  const dataHealthQuery = useQuery<DataHealthEnvelope>({
    queryKey: ['v10', 'parts-intel', 'data-health'],
    queryFn: () => v10PartsIntelApi.getDataHealth(),
    retry: false,
  });

  // V10 backend rejects with 404 when the feature flag is off — surface
  // a clean "feature unavailable" state instead of a generic error.
  const featureDisabled =
    summaryQuery.isError &&
    (summaryQuery.error as { response?: { status?: number } })?.response?.status === 404;

  if (featureDisabled) {
    return (
      <div>
        <PageHeader title="Yedek Parça Zekâsı" description="V10 — okunaklı analitik katmanı" />
        <EmptyState
          variant="default"
          title="Bu özellik henüz açık değil"
          description="V10 yedek parça zekâsı katmanı, FEATURE_V10_PARTS_INTEL bayrağı açıldığında etkinleşir."
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Yedek Parça Zekâsı"
        description="ANEXPO 2026 strateji çerçevesine göre derlenen okunaklı zekâ paneli"
      />

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
        <Card title="Aktif Parça">
          {summaryQuery.isLoading ? (
            <Skeleton variant="line" />
          ) : (
            <p className="text-3xl font-bold text-slate-900 dark:text-white">
              {summaryQuery.data?.total_active_parts ?? 0}
            </p>
          )}
        </Card>
        <Card title="Pareto Dağılımı">
          {summaryQuery.isLoading ? (
            <Skeleton variant="line" />
          ) : (
            <div className="flex flex-wrap items-baseline gap-3 text-sm">
              <Badge variant="success">A: {summaryQuery.data?.tier_counts.A ?? 0}</Badge>
              <Badge variant="info">B: {summaryQuery.data?.tier_counts.B ?? 0}</Badge>
              <Badge variant="default">C: {summaryQuery.data?.tier_counts.C ?? 0}</Badge>
            </div>
          )}
        </Card>
        <Card title="Donmuş Sermaye">
          {summaryQuery.isLoading ? (
            <Skeleton variant="line" />
          ) : (
            <>
              <p className="text-2xl font-bold text-honeywell-red">
                {formatCurrency(summaryQuery.data?.frozen_capital_total ?? 0, 'USD')}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {summaryQuery.data?.dead_stock_count ?? 0} hareketsiz parça
              </p>
            </>
          )}
        </Card>
        <Card title="Veri Sağlığı">
          {dataHealthQuery.isLoading ? (
            <Skeleton variant="line" />
          ) : dataHealthQuery.data ? (
            <>
              <div className="flex items-baseline gap-2">
                <p className="text-3xl font-bold text-slate-900 dark:text-white">
                  {dataHealthQuery.data.value}
                </p>
                <span className="text-sm text-slate-400">/100</span>
              </div>
              <Badge variant={healthTone(dataHealthQuery.data.value)}>
                {dataHealthQuery.data.confidence}
              </Badge>
            </>
          ) : (
            <p className="text-sm text-slate-400">—</p>
          )}
        </Card>
      </div>

      {/* Dead stock + Obsolescence side-by-side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-6">
        <Card
          title="Donmuş Stok Defteri"
          action={<Badge variant="warning">{deadStockQuery.data?.total ?? 0} parça</Badge>}
        >
          {deadStockQuery.isLoading ? (
            <Skeleton variant="table" />
          ) : (
            <DataTable
              columns={[
                {
                  key: 'honeywell_code',
                  header: 'Kod',
                  render: (row) => {
                    const r = row as DeadStockItem;
                    return (
                      <Link
                        to={`/parts/${r.spare_part_id}`}
                        className="text-sm font-mono font-semibold text-honeywell-red hover:underline"
                      >
                        {r.honeywell_code ?? '—'}
                      </Link>
                    );
                  },
                },
                {
                  key: 'name',
                  header: 'İsim',
                  render: (row) => {
                    const r = row as DeadStockItem;
                    return (
                      <span className="text-sm text-slate-700 dark:text-slate-300 line-clamp-1">
                        {r.name ?? '—'}
                      </span>
                    );
                  },
                },
                {
                  key: 'frozen_capital_estimate',
                  header: 'Donmuş',
                  render: (row) => {
                    const r = row as DeadStockItem;
                    return (
                      <span className="text-sm font-mono tabular-nums text-honeywell-red">
                        {formatCurrency(r.frozen_capital_estimate, 'USD')}
                      </span>
                    );
                  },
                },
                {
                  key: 'last_quoted_at',
                  header: 'Son Teklif',
                  render: (row) => {
                    const r = row as DeadStockItem;
                    return (
                      <span className="text-xs text-slate-500">
                        {r.last_quoted_at ? formatDate(r.last_quoted_at) : 'Hiç'}
                      </span>
                    );
                  },
                },
              ]}
              data={deadStockQuery.data?.items ?? []}
              emptyMessage="Donmuş stok yok"
            />
          )}
        </Card>

        <Card
          title="Eskime İzleme (EOL Risk)"
          action={<Badge variant="danger">Top {obsolescenceQuery.data?.total ?? 0}</Badge>}
        >
          {obsolescenceQuery.isLoading ? (
            <Skeleton variant="table" />
          ) : (
            <DataTable
              columns={[
                {
                  key: 'honeywell_code',
                  header: 'Kod',
                  render: (row) => {
                    const r = row as ObsolescenceRow;
                    return (
                      <Link
                        to={`/parts/${r.spare_part_id}`}
                        className="text-sm font-mono font-semibold text-honeywell-red hover:underline"
                      >
                        {r.honeywell_code ?? '—'}
                      </Link>
                    );
                  },
                },
                {
                  key: 'risk_score',
                  header: 'Risk',
                  render: (row) => {
                    const r = row as ObsolescenceRow;
                    return <Badge variant={riskTone(r.risk_score)}>{r.risk_score}</Badge>;
                  },
                },
                {
                  key: 'inactivity_days',
                  header: 'Hareketsizlik',
                  render: (row) => {
                    const r = row as ObsolescenceRow;
                    return (
                      <span className="text-xs text-slate-600">
                        {r.inactivity_days >= 9999 ? '∞' : `${r.inactivity_days} g`}
                      </span>
                    );
                  },
                },
                {
                  key: 'price_age_days',
                  header: 'Fiyat Yaşı',
                  render: (row) => {
                    const r = row as ObsolescenceRow;
                    return (
                      <span className="text-xs text-slate-600">
                        {r.price_age_days >= 9999 ? '∞' : `${r.price_age_days} g`}
                      </span>
                    );
                  },
                },
              ]}
              data={obsolescenceQuery.data?.items ?? []}
              emptyMessage="EOL risk altında parça yok"
            />
          )}
        </Card>
      </div>

      {/* Data health driver breakdown */}
      {dataHealthQuery.data && dataHealthQuery.data.drivers.length > 0 && (
        <Card title="Master Data Sağlığı — Alan Kapsamı">
          <div className="space-y-3">
            {dataHealthQuery.data.drivers.map((driver) => (
              <div key={driver.label}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-700 dark:text-slate-300">{driver.label}</span>
                  <span className="text-xs text-slate-500">
                    {driver.filled_pct?.toFixed(1) ?? '—'}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${
                      (driver.filled_pct ?? 0) >= 75
                        ? 'bg-green-500'
                        : (driver.filled_pct ?? 0) >= 50
                          ? 'bg-amber-500'
                          : 'bg-red-500'
                    }`}
                    style={{ width: `${Math.max(driver.filled_pct ?? 0, 2)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          {dataHealthQuery.data.recommended_actions.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
              <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                Önerilen Aksiyonlar
              </p>
              <ul className="space-y-1.5">
                {dataHealthQuery.data.recommended_actions.map((action, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
                  >
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-honeywell-red" />
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
