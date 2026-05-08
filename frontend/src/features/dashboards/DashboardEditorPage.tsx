import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Save, Play, Plus, Trash2, ArrowLeft, Eye } from 'lucide-react';

import { ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, Tooltip } from 'recharts';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { dashboardsApi, reportsApi } from '../../lib/api';
import type { DashboardConfig, DashboardExecuteResult, ReportTemplate } from '../../lib/types';

const CHART_COLORS = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];

/* ── Transform report data to widget format ── */
function extractWidgetItems(data: unknown): { label: string; value: number }[] {
  if (!data) return [];
  if (Array.isArray(data)) return data as { label: string; value: number }[];
  const rd = data as {
    columns?: string[];
    rows?: Record<string, unknown>[];
    chart_data?: { labels: string[]; values: number[] } | null;
  };
  // Prefer chart_data if available
  if (rd.chart_data?.labels?.length) {
    return rd.chart_data.labels.map((label, i) => ({
      label,
      value: rd.chart_data?.values[i] ?? 0,
    }));
  }
  // Fall back to rows: first column as label, second numeric as value
  if (rd.rows?.length) {
    const cols = rd.columns ?? Object.keys(rd.rows[0]);
    const labelCol = cols[0];
    const valueCol =
      cols.find(
        (c) => c === 'count' || c.startsWith('sum_') || c === 'amount' || c === 'grand_total',
      ) ?? cols[1];
    return rd.rows.map((row) => ({
      label: String(row[labelCol] ?? ''),
      value: Number(row[valueCol] ?? 0),
    }));
  }
  return [];
}

/* ── Funnel Widget ── */
function FunnelWidget({ data }: { data: unknown }) {
  const stages = extractWidgetItems(data);
  const maxVal = stages.reduce((m, s) => Math.max(m, s.value), 1);
  return (
    <div className="space-y-1.5">
      {stages.map((stage, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-24 truncate text-right text-xs text-slate-500">{stage.label}</span>
          <div
            className="h-6 rounded bg-honeywell-red/80 transition-all"
            style={{ width: `${(stage.value / maxVal) * 100}%` }}
          />
          <span className="text-xs font-medium text-slate-700">{stage.value}</span>
        </div>
      ))}
      {stages.length === 0 && <p className="text-xs text-slate-400">Veri yok</p>}
    </div>
  );
}

/* ── Gauge Widget ── */
function GaugeWidget({ data }: { data: unknown }) {
  let pct = 0;
  if (typeof data === 'number') {
    pct = data;
  } else {
    const items = extractWidgetItems(data);
    const total = items.reduce((s, i) => s + i.value, 0);
    pct = items.length > 0 ? Math.round(total / items.length) : 0;
  }
  pct = Math.min(100, Math.max(0, pct));
  const r = 40;
  const circ = Math.PI * r;
  const dash = (pct / 100) * circ;
  const color = pct >= 75 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444';
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="100" height="60" viewBox="0 0 100 60" aria-label={`Gauge: ${pct}%`}>
        <path d="M10,50 A40,40 0 0,1 90,50" fill="none" stroke="#e5e7eb" strokeWidth="8" />
        <path
          d="M10,50 A40,40 0 0,1 90,50"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
        />
      </svg>
      <span className="text-xl font-bold text-slate-800">{Math.round(pct)}%</span>
    </div>
  );
}

/* ── Leaderboard Widget ── */
function LeaderboardWidget({ data }: { data: unknown }) {
  const items = extractWidgetItems(data);
  const rows = items.map((i) => ({ name: i.label, value: i.value }));
  const sorted = [...rows].sort((a, b) => b.value - a.value).slice(0, 10);
  const medalColors = ['text-yellow-500', 'text-slate-400', 'text-amber-700'];
  return (
    <div className="space-y-1">
      {sorted.map((row, i) => (
        <div key={i} className="flex items-center gap-2 rounded px-2 py-1 hover:bg-slate-50">
          <span
            className={`w-5 text-center text-xs font-bold ${medalColors[i] ?? 'text-slate-400'}`}
          >
            {i + 1}
          </span>
          <span className="flex-1 truncate text-sm text-slate-700">{row.name}</span>
          <span className="text-sm font-semibold text-slate-800">{row.value}</span>
        </div>
      ))}
      {sorted.length === 0 && <p className="text-xs text-slate-400">Veri yok</p>}
    </div>
  );
}

/* ── Report/Chart/KPI Widget ── */
function ReportDataWidget({ data, widgetType }: { data: unknown; widgetType: string }) {
  const reportData = data as {
    columns?: string[];
    rows?: Record<string, unknown>[];
    chart_data?: { labels: string[]; values: number[] } | null;
    total?: number;
  } | null;

  if (!reportData) return <p className="text-xs text-slate-400">Veri yok</p>;

  const rows = reportData.rows ?? [];
  const columns = reportData.columns ?? (rows.length > 0 ? Object.keys(rows[0]) : []);
  const chartData = reportData.chart_data;

  // KPI: show summary numbers
  if (widgetType === 'kpi' && rows.length > 0) {
    return (
      <div className="grid grid-cols-2 gap-3">
        {rows.slice(0, 4).map((row, i) => {
          const label = String(Object.values(row)[0] ?? '');
          const value = Object.values(row)[1];
          return (
            <div key={i} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
              <p className="text-xs text-slate-500 truncate">{label}</p>
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {typeof value === 'number' ? value.toLocaleString('tr-TR') : String(value ?? '-')}
              </p>
            </div>
          );
        })}
      </div>
    );
  }

  // Chart: render bar or pie chart from chart_data or rows
  if ((widgetType === 'chart' || widgetType === 'report') && chartData?.labels?.length) {
    const items = chartData.labels.map((label, i) => ({
      label,
      value: chartData.values[i] ?? 0,
    }));
    return (
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={items}>
            <XAxis dataKey="label" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Bar dataKey="value" fill="#ef4444" radius={[4, 4, 0, 0]}>
              {items.map((_, idx) => (
                <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Table fallback for report type
  if (rows.length > 0) {
    return (
      <div className="max-h-48 overflow-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200">
              {columns.map((col) => (
                <th key={col} className="px-2 py-1 text-left font-medium text-slate-500">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 20).map((row, i) => (
              <tr key={i} className="border-b border-slate-100">
                {columns.map((col) => (
                  <td key={col} className="px-2 py-1 text-slate-700 truncate max-w-[120px]">
                    {row[col] != null ? String(row[col]) : '-'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 20 && (
          <p className="text-[10px] text-slate-400 mt-1 px-2">+{rows.length - 20} satir daha</p>
        )}
      </div>
    );
  }

  return <p className="text-xs text-slate-400">Veri yok</p>;
}

interface WidgetDef {
  type: string;
  position: { x: number; y: number; w: number; h: number };
  report_id: number | null;
  config: Record<string, unknown>;
}

export default function DashboardEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const dashboardId = Number(id);

  const { data: dashboardData, isLoading } = useQuery<{ data: DashboardConfig }>({
    queryKey: ['dashboards', dashboardId],
    queryFn: () =>
      dashboardsApi.list().then((res: { data: DashboardConfig[] }) => ({
        data: res.data.find((d) => d.id === dashboardId)!,
      })),
    enabled: !!dashboardId,
  });

  const { data: templatesData } = useQuery<{ data: ReportTemplate[] }>({
    queryKey: ['report-templates'],
    queryFn: () => reportsApi.getTemplates(),
  });

  const [name, setName] = useState('');
  const [widgets, setWidgets] = useState<WidgetDef[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [executeResult, setExecuteResult] = useState<DashboardExecuteResult | null>(null);

  // Initialize from fetched data
  if (dashboardData?.data && !initialized) {
    setName(dashboardData.data.name);
    try {
      const parsed: unknown[] = JSON.parse(dashboardData.data.widgets_json);
      setWidgets(
        parsed.map((w) => {
          const widget = w as Record<string, unknown>;
          return {
            ...widget,
            position: (widget.position as WidgetDef['position'] | undefined) ?? {
              x: 0,
              y: 0,
              w: 6,
              h: 2,
            },
          } as WidgetDef;
        }),
      );
    } catch {
      setWidgets([]);
    }
    setInitialized(true);
  }

  const templates = templatesData?.data ?? [];

  const saveMutation = useMutation({
    mutationFn: () =>
      dashboardsApi.update(dashboardId, {
        name,
        widgets_json: JSON.stringify(widgets),
      }),
    onSuccess: () => {
      toast.success('Pano kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['dashboards'] });
    },
    onError: () => toast.error('Kaydedilemedi'),
  });

  const executeMutation = useMutation({
    mutationFn: async () => {
      // Save current state first, then execute
      await dashboardsApi.update(dashboardId, {
        name,
        widgets_json: JSON.stringify(widgets),
      });
      return dashboardsApi.execute(dashboardId);
    },
    onSuccess: (data) => {
      const result = data?.data ?? data;
      setExecuteResult({
        ...result,
        widgets: result?.widgets ?? [],
      });
      queryClient.invalidateQueries({ queryKey: ['dashboards'] });
      toast.success('Pano kaydedildi ve calistirildi');
    },
    onError: () => toast.error('Calistirilamadi'),
  });

  const addWidget = () => {
    setWidgets([
      ...widgets,
      {
        type: 'report',
        position: { x: 0, y: widgets.length, w: 6, h: 4 },
        report_id: null,
        config: {},
      },
    ]);
  };

  const removeWidget = (index: number) => {
    setWidgets(widgets.filter((_, i) => i !== index));
  };

  const updateWidget = (index: number, updates: Partial<WidgetDef>) => {
    setWidgets(widgets.map((w, i) => (i === index ? { ...w, ...updates } : w)));
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="line" />
        <Skeleton variant="card" />
        <Skeleton variant="card" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Pano Duzenleyici" description={name || 'Yeni Pano'}>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => navigate('/dashboards')}>
            <ArrowLeft size={16} className="mr-1" /> Geri
          </Button>
          {/* Round-9 — quick switch from edit → run/view. */}
          <Button variant="ghost" onClick={() => navigate(`/dashboards/${dashboardId}`)}>
            <Eye size={16} className="mr-1" /> Görüntüle
          </Button>
          <Button
            variant="secondary"
            onClick={() => executeMutation.mutate()}
            loading={executeMutation.isPending}
          >
            <Play size={16} className="mr-1" /> Calistir
          </Button>
          <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
            <Save size={16} className="mr-1" /> Kaydet
          </Button>
        </div>
      </PageHeader>

      {/* Dashboard Name */}
      <div className="mb-6 max-w-md">
        <Input label="Pano Adi" value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      {/* Widget List */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Widget&apos;lar ({widgets.length})</h2>
        <Button variant="secondary" size="sm" onClick={addWidget}>
          <Plus size={14} className="mr-1" /> Widget Ekle
        </Button>
      </div>

      {widgets.length === 0 ? (
        <Card>
          <div className="p-8 text-center text-sm text-slate-500">
            Henüz widget eklenmedi. &quot;Widget Ekle&quot; butonuna tiklayarak baslayabilirsiniz.
          </div>
        </Card>
      ) : (
        <div className="space-y-3">
          {widgets.map((widget, index) => (
            <Card key={index}>
              <div className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="info" size="sm">
                      Widget {index + 1}
                    </Badge>
                    <span className="text-xs text-slate-400">
                      Konum: ({widget.position?.x ?? 0}, {widget.position?.y ?? 0}) Boyut:{' '}
                      {widget.position?.w ?? 6}x{widget.position?.h ?? 2}
                    </span>
                  </div>
                  <button
                    onClick={() => removeWidget(index)}
                    className="rounded p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Tip</label>
                    <select
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                      value={widget.type}
                      onChange={(e) => updateWidget(index, { type: e.target.value })}
                    >
                      <option value="report">Rapor</option>
                      <option value="kpi">KPI Karti</option>
                      <option value="chart">Grafik</option>
                      <option value="funnel">Huni (Funnel)</option>
                      <option value="gauge">Gösterge (Gauge)</option>
                      <option value="leaderboard">Liderlik Tablosu</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Rapor Şablonu
                    </label>
                    <select
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                      value={widget.report_id ?? ''}
                      onChange={(e) =>
                        updateWidget(index, {
                          report_id: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                    >
                      <option value="">-- Seç --</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Execute Results */}
      {executeResult && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Calistirma Sonuclari</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {executeResult.widgets.map((w, i) => (
              <Card key={i}>
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <Badge variant="info" size="sm">
                      Widget {i + 1} - {w.type}
                    </Badge>
                    {w.error && (
                      <Badge variant="danger" size="sm">
                        Hata
                      </Badge>
                    )}
                  </div>
                  {w.error ? (
                    <p className="text-sm text-red-600">{w.error}</p>
                  ) : w.type === 'funnel' ? (
                    <FunnelWidget data={w.data} />
                  ) : w.type === 'gauge' ? (
                    <GaugeWidget data={w.data} />
                  ) : w.type === 'leaderboard' ? (
                    <LeaderboardWidget data={w.data} />
                  ) : w.data != null ? (
                    <ReportDataWidget data={w.data} widgetType={w.type} />
                  ) : w.report_id ? (
                    <div className="text-sm text-slate-500 space-y-1">
                      <p>
                        <span className="font-medium">Tip:</span> {w.type}
                      </p>
                      <p>
                        <span className="font-medium">Rapor ID:</span> {w.report_id}
                      </p>
                      <p className="text-xs text-amber-600 italic">
                        Rapor verisi yuklenemedi veya boş.
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-400 italic">
                      Widget için rapor sablonu secilmedi.
                    </p>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
