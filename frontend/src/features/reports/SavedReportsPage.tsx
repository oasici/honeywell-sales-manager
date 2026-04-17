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

  const { data, isLoading } = useQuery<{ data: ReportTemplate[] }>({
    queryKey: ['report-templates'],
    queryFn: reportsApi.getTemplates,
  });

  const templates: ReportTemplate[] =
    data?.data ?? (Array.isArray(data) ? (data as ReportTemplate[]) : []);

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
      <PageHeader title="Raporlar" description="Kaydedilmis raporlarinizi yonetin">
        <Button onClick={() => navigate('/reports/builder')}>
          <Plus size={16} className="mr-1.5" />
          Yeni Rapor
        </Button>
      </PageHeader>

      {templates.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-center">
          <BarChart3 size={48} className="mb-3 text-gray-300 dark:text-gray-600" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Henüz rapor yok</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Yeni bir rapor olusturarak baslayabilirsiniz
          </p>
          <Button className="mt-4" onClick={() => navigate('/reports/builder')}>
            Rapor Oluştur
          </Button>
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
                className="rounded-xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md dark:border-gray-700 dark:bg-gray-800"
              >
                <div className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <h4 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                        {template.name}
                      </h4>
                      {template.description && (
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                          {template.description}
                        </p>
                      )}
                    </div>
                    <ChartIcon size={20} className="ml-2 shrink-0 text-gray-400" />
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <Badge variant={entityBadge.variant} size="sm">
                      {entityBadge.label}
                    </Badge>
                    {template.is_public ? (
                      <Badge variant="info" size="sm">
                        <Globe size={10} className="mr-1" />
                        Herkese Acik
                      </Badge>
                    ) : (
                      <Badge variant="default" size="sm">
                        <Lock size={10} className="mr-1" />
                        Özel
                      </Badge>
                    )}
                    {template.is_system && (
                      <Badge variant="warning" size="sm">
                        <Settings2 size={10} className="mr-1" />
                        Sistem
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="flex items-center border-t border-gray-100 dark:border-gray-700">
                  <button
                    type="button"
                    onClick={() => navigate(`/reports/view/${template.id}`)}
                    className="flex flex-1 items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-green-600 hover:bg-green-50 transition-colors dark:hover:bg-green-900/20"
                  >
                    <Play size={12} />
                    Calistir
                  </button>
                  <div className="h-8 w-px bg-gray-100 dark:bg-gray-700" />
                  <button
                    type="button"
                    onClick={() => handleExportCsv(template.id)}
                    className="flex flex-1 items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-blue-600 hover:bg-blue-50 transition-colors dark:hover:bg-blue-900/20"
                  >
                    <Download size={12} />
                    CSV
                  </button>
                  <div className="h-8 w-px bg-gray-100 dark:bg-gray-700" />
                  <button
                    type="button"
                    onClick={() => handleExportExcel(template.id, template.name)}
                    className="flex flex-1 items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-emerald-600 hover:bg-emerald-50 transition-colors dark:hover:bg-emerald-900/20"
                  >
                    <Download size={12} />
                    Excel Indir
                  </button>
                  {!template.is_system && (
                    <>
                      <div className="h-8 w-px bg-gray-100 dark:bg-gray-700" />
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(template)}
                        className="flex flex-1 items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-red-500 hover:bg-red-50 transition-colors dark:hover:bg-red-900/20"
                      >
                        <Trash2 size={12} />
                        Sil
                      </button>
                    </>
                  )}
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
