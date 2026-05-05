import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Play,
  Download,
  Trash2,
  BarChart3,
  Globe,
  Lock,
  Settings2,
  LineChart,
  PieChart,
  Table,
} from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { reportsApi } from '../../lib/api';
import type { ReportTemplate } from '../../lib/types';
import { useState } from 'react';

const ENTITY_TYPE_BADGE: Record<
  string,
  { label: string; variant: 'info' | 'success' | 'warning' | 'danger' | 'default' }
> = {
  quote: { label: 'Teklif', variant: 'info' },
  opportunity: { label: 'Fırsat', variant: 'success' },
  customer: { label: 'Müşteri', variant: 'warning' },
  email: { label: 'Email', variant: 'danger' },
};

const CHART_TYPE_ICONS: Record<string, typeof BarChart3> = {
  bar: BarChart3,
  line: LineChart,
  pie: PieChart,
  table: Table,
};

export default function SavedReportsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<ReportTemplate | null>(null);

  const { data, isLoading } = useQuery<{
    items?: ReportTemplate[];
    data?: ReportTemplate[];
  }>({
    queryKey: ['report-templates'],
    queryFn: reportsApi.getTemplates,
  });

  // Round-5 Phase 7 — backend canonicalized to ``items``; legacy
  // ``data`` retained server-side as additive bridge.
  const templates: ReportTemplate[] =
    data?.items ??
    data?.data ??
    (Array.isArray(data) ? (data as ReportTemplate[]) : []);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => reportsApi.deleteTemplate(id),
    onSuccess: () => {
      toast.success('Rapor şablonu silindi');
      queryClient.invalidateQueries({ queryKey: ['report-templates'] });
      setDeleteTarget(null);
    },
    onError: () => toast.error('Rapor silinemedi'),
  });

  const handleExportExcel = async (id: number, name: string) => {
    try {
      await reportsApi.exportExcel(id, name);
      toast.success('Excel indirildi');
    } catch {
      toast.error('Excel indirilemedi');
    }
  };

  const handleExportCsv = async (id: number) => {
    try {
      const result = await reportsApi.exportCsv(id);
      const csvContent = typeof result === 'string' ? result : JSON.stringify(result);
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `report-${id}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('CSV indirildi');
    } catch {
      toast.error('CSV indirilemedi');
    }
  };

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Raporlar" description="Kaydedilmis raporlarinizi yonetin" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton variant="card" count={3} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Raporlar" description="Kaydedilmiş raporlarınızı yönetin">
        <Button onClick={() => navigate('/reports/builder')}>
          <Plus size={14} />
          Yeni Rapor
        </Button>
      </PageHeader>

      {templates.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<BarChart3 size={20} />}
            title="Henüz rapor yok"
            description="Yeni bir rapor şablonu oluşturarak başlayabilirsiniz."
            action={
              <Button onClick={() => navigate('/reports/builder')} variant="secondary">
                <Plus size={14} />
                Rapor Oluştur
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((template) => {
            const entityBadge = ENTITY_TYPE_BADGE[template.entity_type] || {
              label: template.entity_type,
              variant: 'default' as const,
            };
            const ChartIcon = CHART_TYPE_ICONS[template.chart_type || 'table'] || Table;

            return (
              <div
                key={template.id}
                className="group flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) dark:border-slate-800 dark:bg-slate-900"
              >
                <button
                  type="button"
                  onClick={() => navigate(`/reports/view/${template.id}`)}
                  className="flex flex-1 flex-col gap-3 p-5 text-left"
                >
                  <div className="flex items-start gap-3">
                    <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                      <ChartIcon size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h4 className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                        {template.name}
                      </h4>
                      {template.description && (
                        <p className="mt-1 line-clamp-2 text-[12px] text-slate-500 dark:text-slate-400">
                          {template.description}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant={entityBadge.variant} size="sm">
                      {entityBadge.label}
                    </Badge>
                    {template.is_public ? (
                      <Badge variant="info" size="sm">
                        <Globe size={10} />
                        Herkese Açık
                      </Badge>
                    ) : (
                      <Badge variant="default" size="sm">
                        <Lock size={10} />
                        Özel
                      </Badge>
                    )}
                    {template.is_system && (
                      <Badge variant="warning" size="sm">
                        <Settings2 size={10} />
                        Sistem
                      </Badge>
                    )}
                  </div>

                  {(template as unknown as { last_run_at?: string }).last_run_at && (
                    <p className="text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                      Son çalıştırma:{' '}
                      <span className="text-slate-600 dark:text-slate-300">
                        {new Date(
                          (template as unknown as { last_run_at: string }).last_run_at,
                        ).toLocaleString('tr-TR')}
                      </span>
                    </p>
                  )}
                </button>

                {/* Action row — primary "Çalıştır" + secondary CSV/Excel +
                    destructive delete (only when non-system). Slate footer
                    so the buttons read as a contained tool palette rather
                    than a stack of links. */}
                <div className="flex items-center justify-end gap-1.5 border-t border-slate-100 bg-slate-50/50 px-3 py-2.5 dark:border-slate-800 dark:bg-slate-900/40">
                  <Button
                    variant="tertiary"
                    size="sm"
                    onClick={() => handleExportCsv(template.id)}
                    title="CSV indir"
                  >
                    <Download size={13} />
                    CSV
                  </Button>
                  <Button
                    variant="tertiary"
                    size="sm"
                    onClick={() => handleExportExcel(template.id, template.name)}
                    title="Excel indir"
                  >
                    <Download size={13} />
                    Excel
                  </Button>
                  {!template.is_system && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteTarget(template)}
                      aria-label="Sil"
                    >
                      <Trash2 size={13} className="text-red-500" />
                    </Button>
                  )}
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => navigate(`/reports/view/${template.id}`)}
                  >
                    <Play size={13} />
                    Çalıştır
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id);
          }
        }}
        title="Rapor Sablonunu Sil"
        message={`"${deleteTarget?.name}" rapor şablonu silinecek. Devam etmek istiyor musunuz?`}
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
