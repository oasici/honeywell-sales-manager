import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, RefreshCw, Pencil, Download } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, Tooltip } from 'recharts';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { dashboardsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import type { DashboardConfig, DashboardExecuteResult } from '../../lib/types';

/**
 * Round-9 — read-only dashboard viewer.
 *
 * Card click on the list page lands here; the executed widget output is
 * the canonical "view" experience. Editing is reachable via the pencil
 * button which routes to ``/dashboards/:id/edit``.
 *
 * Download exports the executed result as JSON and as CSV (one CSV per
 * widget that returns tabular rows).
 */

const CHART_COLORS = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];

interface ExecutedWidget {
  widget_id?: string;
  title?: string;
  type?: string;
  value?: number | string;
  data?: unknown;
  total?: number;
  count?: number;
  error?: string;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function rowsToCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const escape = (cell: unknown): string => {
    if (cell === null || cell === undefined) return '';
    const str = String(cell);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const header = columns.join(',');
  const body = rows
    .map((row) => columns.map((c) => escape(row[c])).join(','))
    .join('\n');
  return `${header}\n${body}`;
}

interface ViewerWidgetProps {
  widget: ExecutedWidget;
}

function ViewerWidget({ widget }: ViewerWidgetProps) {
  const data = widget.data as
    | {
        columns?: string[];
        rows?: Record<string, unknown>[];
        chart_data?: { labels: string[]; values: number[] } | null;
        total?: number;
      }
    | null;

  if (widget.error) {
    return (
      <Card title={widget.title ?? widget.type ?? 'Widget'}>
        <p className="text-caption text-warning">Hata: {widget.error}</p>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title={widget.title ?? widget.type ?? 'Widget'}>
        <p className="text-caption text-slate-400">Veri yok</p>
      </Card>
    );
  }

  const widgetType = widget.type ?? 'report';
  const rows = data.rows ?? [];
  const columns = data.columns ?? (rows.length > 0 ? Object.keys(rows[0]) : []);
  const chartData = data.chart_data;

  // KPI block
  if (widgetType === 'kpi' && rows.length > 0) {
    return (
      <Card title={widget.title ?? 'KPI'}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {rows.slice(0, 8).map((row, i) => {
            const label = String(Object.values(row)[0] ?? '');
            const value = Object.values(row)[1];
            return (
              <div key={i} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
                <p className="text-xs text-slate-500 truncate">{label}</p>
                <p className="text-lg font-bold tabular-nums text-slate-900 dark:text-white">
                  {typeof value === 'number' ? value.toLocaleString('tr-TR') : String(value ?? '-')}
                </p>
              </div>
            );
          })}
        </div>
      </Card>
    );
  }

  // Chart block
  if ((widgetType === 'chart' || widgetType === 'report') && chartData?.labels?.length) {
    const items = chartData.labels.map((label, i) => ({
      label,
      value: chartData.values[i] ?? 0,
    }));
    return (
      <Card title={widget.title ?? 'Grafik'} description={`${items.length} öge`}>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={items}>
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {items.map((_, idx) => (
                  <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    );
  }

  // Table fallback
  if (rows.length > 0) {
    return (
      <Card title={widget.title ?? 'Tablo'} description={`${rows.length} satır`}>
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
              <tr className="border-b border-slate-200 dark:border-slate-700">
                {columns.map((col) => (
                  <th key={col} className="px-3 py-2 text-left text-overline text-slate-500">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
                  {columns.map((col) => (
                    <td
                      key={col}
                      className="px-3 py-2 text-slate-700 dark:text-slate-300 truncate max-w-[240px]"
                    >
                      {row[col] != null ? String(row[col]) : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    );
  }

  return (
    <Card title={widget.title ?? 'Widget'}>
      <p className="text-caption text-slate-400">Veri yok</p>
    </Card>
  );
}

export default function DashboardViewerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const dashboardId = Number(id);
  const [executedAt, setExecutedAt] = useState<Date | null>(null);

  const dashboardQuery = useQuery<{ data: DashboardConfig }>({
    queryKey: ['dashboards', dashboardId],
    queryFn: () =>
      dashboardsApi.list().then((res: { data: DashboardConfig[] }) => ({
        data: res.data.find((d) => d.id === dashboardId)!,
      })),
    enabled: dashboardId > 0,
  });

  const executeQuery = useQuery<{ data: DashboardExecuteResult } | DashboardExecuteResult>({
    queryKey: ['dashboard-execute', dashboardId],
    queryFn: () => dashboardsApi.execute(dashboardId),
    enabled: dashboardId > 0,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (executeQuery.dataUpdatedAt) {
      setExecutedAt(new Date(executeQuery.dataUpdatedAt));
    }
  }, [executeQuery.dataUpdatedAt]);

  const dashboard = dashboardQuery.data?.data;
  const result =
    (executeQuery.data && 'data' in executeQuery.data ? executeQuery.data.data : executeQuery.data) ??
    null;
  const widgets = (result?.widgets ?? []) as ExecutedWidget[];

  const handleDownloadJson = () => {
    if (!result) return;
    const payload = JSON.stringify(
      {
        dashboard: { id: dashboard?.id, name: dashboard?.name },
        executed_at: executedAt?.toISOString() ?? null,
        widgets,
      },
      null,
      2,
    );
    const slug = (dashboard?.name ?? `dashboard-${dashboardId}`)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-');
    downloadBlob(
      new Blob([payload], { type: 'application/json;charset=utf-8' }),
      `${slug}-${dashboardId}.json`,
    );
  };

  const handleDownloadCsv = () => {
    const tabular = widgets.filter((w) => {
      const d = w.data as { rows?: unknown[]; columns?: unknown[] } | null;
      return Array.isArray(d?.rows) && d!.rows!.length > 0 && Array.isArray(d?.columns);
    });
    if (tabular.length === 0) return;
    const slug = (dashboard?.name ?? `dashboard-${dashboardId}`)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-');
    if (tabular.length === 1) {
      const w = tabular[0];
      const d = w.data as { rows: Record<string, unknown>[]; columns: string[] };
      downloadBlob(
        new Blob([rowsToCsv(d.columns, d.rows)], { type: 'text/csv;charset=utf-8' }),
        `${slug}-${w.title ?? w.widget_id ?? 'widget'}.csv`,
      );
      return;
    }
    // Multiple tabular widgets — concatenate with header sections.
    const sections: string[] = [];
    for (const w of tabular) {
      const d = w.data as { rows: Record<string, unknown>[]; columns: string[] };
      sections.push(`# ${w.title ?? w.type ?? 'widget'}`);
      sections.push(rowsToCsv(d.columns, d.rows));
      sections.push('');
    }
    downloadBlob(
      new Blob([sections.join('\n')], { type: 'text/csv;charset=utf-8' }),
      `${slug}-export.csv`,
    );
  };

  if (dashboardQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="space-y-4">
        <PageHeader title="Pano bulunamadı" />
        <EmptyState
          title="Pano bulunamadı"
          description="Bu kayıt silinmiş ya da erişiminiz olmayabilir."
          action={
            <Button onClick={() => navigate('/dashboards')}>
              <ArrowLeft size={14} />
              Listeye dön
            </Button>
          }
        />
      </div>
    );
  }

  const hasTabular = widgets.some((w) => {
    const d = w.data as { rows?: unknown[] } | null;
    return Array.isArray(d?.rows) && d!.rows!.length > 0;
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title={dashboard.name}
        description="Çalıştırılmış pano görünümü"
        eyebrow="Panolar"
      >
        <Button
          variant="tertiary"
          size="sm"
          onClick={() => executeQuery.refetch()}
          disabled={executeQuery.isFetching}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${executeQuery.isFetching ? 'animate-spin' : ''}`} />
          Yenile
        </Button>
        <Button
          variant="tertiary"
          size="sm"
          onClick={handleDownloadJson}
          disabled={!result}
        >
          <Download className="mr-1 h-3 w-3" />
          JSON indir
        </Button>
        {hasTabular && (
          <Button
            variant="tertiary"
            size="sm"
            onClick={handleDownloadCsv}
            disabled={!result}
          >
            <Download className="mr-1 h-3 w-3" />
            CSV indir
          </Button>
        )}
        <Button
          variant="primary"
          size="sm"
          onClick={() => navigate(`/dashboards/${dashboardId}/edit`)}
        >
          <Pencil className="mr-1 h-3 w-3" />
          Düzenle
        </Button>
      </PageHeader>

      {executedAt && (
        <p className="text-caption text-slate-500">
          Son çalıştırma: <span className="tabular-nums">{formatDateTime(executedAt.toISOString())}</span>
          {dashboard.is_default && (
            <Badge variant="warning" className="ml-2">
              Varsayılan
            </Badge>
          )}
        </p>
      )}

      {executeQuery.isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {!executeQuery.isLoading && widgets.length === 0 && (
        <EmptyState
          title="Bu panoda henüz widget yok"
          description="Düzenleme moduna geçerek widget ekleyin."
          action={
            <Button onClick={() => navigate(`/dashboards/${dashboardId}/edit`)}>
              <Pencil size={14} />
              Düzenle
            </Button>
          }
        />
      )}

      {widgets.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {widgets.map((w, i) => (
            <ViewerWidget key={w.widget_id ?? i} widget={w} />
          ))}
        </div>
      )}
    </div>
  );
}
