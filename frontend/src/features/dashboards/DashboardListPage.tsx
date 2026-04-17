import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, LayoutGrid, Trash2, Star } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { dashboardsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import type { DashboardConfig } from '../../lib/types';

export default function DashboardListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({ name: '', widgets_json: '[]', is_default: false });

  const { data, isLoading } = useQuery<{ data: DashboardConfig[] }>({
    queryKey: ['dashboards'],
    queryFn: () => dashboardsApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => dashboardsApi.create(payload),
    onSuccess: (result: { data: DashboardConfig }) => {
      toast.success('Pano oluşturuldu');
      setModalOpen(false);
      setForm({ name: '', widgets_json: '[]', is_default: false });
      queryClient.invalidateQueries({ queryKey: ['dashboards'] });
      navigate(`/dashboards/${result.data.id}`);
    },
    onError: () => toast.error('Pano oluşturulamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dashboardsApi.remove(id),
    onSuccess: () => {
      toast.success('Pano silindi');
      queryClient.invalidateQueries({ queryKey: ['dashboards'] });
    },
    onError: () => toast.error('Pano silinemedi'),
  });

  const dashboards = data?.data ?? [];

  return (
    <div>
      <PageHeader title="Panolar" description="Özel rapor panolari olusturun ve yonetin">
        <Button onClick={() => setModalOpen(true)}>
          <Plus size={16} className="mr-1" /> Yeni Pano
        </Button>
      </PageHeader>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} variant="card" />)}
        </div>
      ) : dashboards.length === 0 ? (
        <EmptyState
          title="Henüz pano yok"
          description="Raporlarinizi bir araya getirmek için pano olusturun"
          action={<Button onClick={() => setModalOpen(true)}>Pano Oluştur</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {dashboards.map((d) => (
            <Card key={d.id}>
              <div
                className="p-5 cursor-pointer hover:bg-gray-50 transition-colors"
                onClick={() => navigate(`/dashboards/${d.id}`)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <LayoutGrid size={18} className="text-honeywell-red" />
                    <h3 className="text-sm font-semibold text-gray-900">{d.name}</h3>
                  </div>
                  {d.is_default && (
                    <Badge variant="warning" size="sm">
                      <Star size={10} className="mr-0.5" /> Varsayılan
                    </Badge>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">
                    {d.created_at ? formatDateTime(d.created_at) : '—'}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('Bu panoyu silmek istediginize emin misiniz?')) {
                        deleteMutation.mutate(d.id);
                      }
                    }}
                    className="rounded p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Yeni Pano" size="md">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate({
              name: form.name,
              widgets_json: form.widgets_json,
              is_default: form.is_default,
            });
          }}
          className="space-y-4"
        >
          <Input
            label="Pano Adi"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              className="rounded border-gray-300"
            />
            Varsayılan pano olarak ayarla
          </label>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>İptal</Button>
            <Button type="submit" loading={createMutation.isPending}>Oluştur</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
