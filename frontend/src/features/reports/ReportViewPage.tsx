import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Printer, ArrowLeft } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { reportsApi } from '../../lib/api';
import type { ReportTemplate } from '../../lib/types';

const CHART_COLORS = [
  '#ef4444',
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
  '#f97316',
  '#6366f1',
];

const ENTITY_TYPE_LABELS: Record<string, string> = {
  quote: 'Teklif',
  opportunity: 'Firsat',
  customer: 'Musteri',
  email: 'Email',
};

interface ExecuteResult {
  rows?: Record<string, unknown>[];
  data?: Record<string, unknown>[] | { rows?: Record<string, unknown>[]; columns?: string[] };
  columns?: string[];
}

export default function ReportViewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const reportId = Number(id);

  const { data: templateData, isLoading: isTemplateLoading } = useQuery<ReportTemplate>({
    queryKey: ['report-template', reportId],
    queryFn: async () => {
      const allTemplates = await reportsApi.getTemplates();
      const templates: ReportTemplate[] =
        allTemplates?.data ?? (Array.isArray(allTemplates) ? allTemplates : []);
      const found = templates.find((t: ReportTemplate) => t.id === reportId);
      if (!found) throw new Error('Template not found');
      return found;
    },
    enabled: !!reportId,
  });

  const { data: executeData, isLoading: isExecuting } = useQuery<ExecuteResult>({
    queryKey: ['report-execute', reportId],
    queryFn: () => reportsApi.execute(reportId),
    enabled: !!reportId,
  });

  const handleExportCsv = async () => {
    try {
      const result = await reportsApi.exportCsv(reportId);
      const csvContent = typeof result === 'string' ? result : JSON.stringify(result);
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `report-${reportId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('CSV indirildi');
    } catch {
      toast.error('CSV indirilemedi');
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (isTemplateLoading || isExecuting) {
    return (
      <div>
        <PageHeader title="Rapor Yukleniyor..." />
        <div className="space-y-4">
          <Skeleton variant="card" count={2} />
        </div>
      </div>
    );
  }

  const rawData = executeData?.data;
  const nestedRows =
    rawData !== undefined && !Array.isArray(rawData)
      ? (rawData as { rows?: Record<string, unknown>[] }).rows
      : undefined;
  const nestedColumns =
    rawData !== undefined && !Array.isArray(rawData)
      ? (rawData as { columns?: string[] }).columns
      : undefined;

  const rows: Record<string, unknown>[] =
    executeData?.rows ??
    nestedRows ??
    (Array.isArray(rawData) ? (rawData as Record<string, unknown>[]) : []);

  let columns: string[] = executeData?.columns ?? nestedColumns ?? [];
  if (columns.length === 0 && templateData?.columns_json) {
    try {
      columns = JSON.parse(templateData.columns_json);
    } catch {
      columns = [];
    }
  }
  if (columns.length === 0 && rows.length > 0) {
    columns = Object.keys(rows[0]);
  }

  const chartType = templateData?.chart_type || 'table';
  const groupByKey = templateData?.group_by || columns[0] || '';
  const NUMERIC_PRIORITIES = [
    'count',
    'sum_grand_total',
    'sum_amount',
    'avg_grand_total',
    'avg_amount',
    'grand_total',
    'amount',
    'value',
    'total',
    'category_confidence',
  ];
  const valueKey =
    NUMERIC_PRIORITIES.find((p) => columns.includes(p)) || columns[1] || columns[0] || '';

  return (
    <div>
      <PageHeader
        title={templateData?.name || `Rapor #${reportId}`}
        description={
          templateData?.entity_type
            ? ENTITY_TYPE_LABELS[templateData.entity_type] || templateData.entity_type
            : undefined
        }
      >
        {templateData?.entity_type && (
          <Badge variant="info">
            {ENTITY_TYPE_LABELS[templateData.entity_type] || templateData.entity_type}
          </Badge>
        )}
        <Button variant="secondary" onClick={handleExportCsv}>
          <Download size={16} className="mr-1.5" />
          CSV Indir
        </Button>
        <Button variant="secondary" onClick={handlePrint}>
          <Printer size={16} className="mr-1.5" />
          Yazdir
        </Button>
        <Button variant="secondary" onClick={() => navigate(-1)}>
          <ArrowLeft size={16} className="mr-1.5" />
          Geri
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Chart */}
        {chartType !== 'table' && rows.length > 0 && groupByKey && valueKey && (
          <Card title="Grafik">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                {chartType === 'bar' ? (
                  <BarChart data={rows}>
                    <XAxis dataKey={groupByKey} tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey={valueKey} fill="#ef4444" radius={[4, 4, 0, 0]} />
                  </BarChart>
                ) : chartType === 'line' ? (
                  <LineChart data={rows}>
                    <XAxis dataKey={groupByKey} tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey={valueKey}
                      stroke="#ef4444"
                      strokeWidth={2}
                      dot={{ fill: '#ef4444' }}
                    />
                  </LineChart>
                ) : (
                  <PieChart>
                    <Pie
                      data={rows}
                      dataKey={valueKey}
                      nameKey={groupByKey}
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      label
                    >
                      {rows.map((_, idx) => (
                        <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                )}
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {/* Data Table */}
        <Card title="Veri Tablosu">
          <DataTable
            columns={columns.map((col) => ({
              key: col,
              header: col,
              sortable: true,
            }))}
            data={rows}
            emptyMessage="Rapor verisi bulunamadi"
          />
        </Card>
      </div>
    </div>
  );
}
