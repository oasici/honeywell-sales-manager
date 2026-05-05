import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { complianceApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { BreachNotification } from '../../lib/types';

type BreachStatus = 'open' | 'investigating' | 'notified' | 'closed';
type BreachSeverity = 'low' | 'medium' | 'high' | 'critical';

const STATUS_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'open', label: 'Acik' },
  { value: 'investigating', label: 'Inceleniyor' },
  { value: 'notified', label: 'Bildirildi' },
  { value: 'closed', label: 'Kapatildi' },
];

const STATUS_CHANGE_OPTIONS = [
  { value: 'open', label: 'Acik' },
  { value: 'investigating', label: 'Inceleniyor' },
  { value: 'notified', label: 'Bildirildi' },
  { value: 'closed', label: 'Kapatildi' },
];

const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Düşük' },
  { value: 'medium', label: 'Orta' },
  { value: 'high', label: 'Yüksek' },
  { value: 'critical', label: 'Kritik' },
];

const SEVERITY_VARIANT: Record<BreachSeverity, 'default' | 'info' | 'warning' | 'danger'> = {
  low: 'default',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
};

const STATUS_VARIANT: Record<BreachStatus, 'danger' | 'warning' | 'info' | 'success'> = {
  open: 'danger',
  investigating: 'warning',
  notified: 'info',
  closed: 'success',
};

const INITIAL_FORM = {
  breach_type: '',
  description: '',
  severity: 'medium',
};

export default function BreachWorkflowPage() {
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

  // R5-API-8 — backend canonicalized to {items, total, ...}; legacy
  // ``breaches`` retained server-side as additive bridge during the
  // rollout window. Type widened to accept either shape.
  const { data, isLoading } = useQuery<{
    items?: BreachNotification[];
    breaches?: BreachNotification[];
  }>({
    queryKey: ['compliance', 'breaches', statusFilter],
    queryFn: () => complianceApi.listBreaches(statusFilter || undefined),
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => complianceApi.createBreach(payload),
    onSuccess: () => {
      toast.success('Ihlal bildirimi oluşturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['compliance', 'breaches'] });
    },
    onError: () => toast.error('Ihlal bildirimi oluşturulamadı'),
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      complianceApi.updateBreach(id, { status }),
    onSuccess: () => {
      toast.success('Durum guncellendi');
      queryClient.invalidateQueries({ queryKey: ['compliance', 'breaches'] });
    },
    onError: () => toast.error('Durum guncellenemedi'),
  });

  function handleCreate() {
    if (!form.breach_type.trim()) {
      toast.error('Ihlal tipi zorunludur');
      return;
    }
    createMutation.mutate(form);
  }

  function handleStatusChange(id: number, newStatus: string) {
    updateStatusMutation.mutate({ id, status: newStatus });
  }

  // Round-5 Phase 7 — backend canonicalized to ``items``; legacy
  // ``breaches`` retained server-side as additive bridge. Explicit
  // annotation so .map(breach) keeps its type after the union.
  const breaches: BreachNotification[] = data?.items ?? data?.breaches ?? [];

  const statusLabel = (status: string) =>
    STATUS_CHANGE_OPTIONS.find((o) => o.value === status)?.label ?? status;

  const severityLabel = (severity: string) =>
    SEVERITY_OPTIONS.find((o) => o.value === severity)?.label ?? severity;

  return (
    <div>
      <PageHeader
        title="Ihlal Bildirimleri"
        description="Veri ihlali bildirimlerini takip edin ve yonetin"
      >
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Ihlal Bildirimi</Button>
      </PageHeader>

      {/* Status filter */}
      <div className="mb-6 max-w-xs">
        <Select
          label="Durum Filtresi"
          options={STATUS_OPTIONS}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        />
      </div>

      {isLoading && <Skeleton variant="card" count={3} />}

      {!isLoading && breaches.length === 0 && (
        <EmptyState
          title="Ihlal bildirimi bulunamadi"
          description="Seçilen filtreye uygun ihlal bildirimi yok"
        />
      )}

      {!isLoading && breaches.length > 0 && (
        <div className="space-y-4">
          {breaches.map((breach) => (
            <Card key={breach.id}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {breach.breach_type}
                  </h3>
                  {breach.description && (
                    <p className="text-sm text-slate-600">{breach.description}</p>
                  )}
                  <p className="text-xs text-slate-400">
                    {breach.created_at ? formatDateTime(breach.created_at) : '-'}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={SEVERITY_VARIANT[breach.severity as BreachSeverity] ?? 'default'}>
                    {severityLabel(breach.severity)}
                  </Badge>
                  <Badge variant={STATUS_VARIANT[breach.status as BreachStatus] ?? 'default'}>
                    {statusLabel(breach.status)}
                  </Badge>

                  <Select
                    options={STATUS_CHANGE_OPTIONS}
                    value={breach.status}
                    onChange={(e) => handleStatusChange(breach.id, e.target.value)}
                    aria-label={`Ihlal #${breach.id} durumunu degistir`}
                  />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Ihlal Bildirimi"
      >
        <div className="space-y-4">
          <Input
            label="Ihlal Tipi"
            placeholder="Örneğin: Yetkisiz erişim"
            value={form.breach_type}
            onChange={(e) => setForm({ ...form, breach_type: e.target.value })}
          />
          <Input
            label="Açıklama"
            placeholder="Ihlal detaylarini giriniz"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <Select
            label="Ciddiyet"
            options={SEVERITY_OPTIONS}
            value={form.severity}
            onChange={(e) => setForm({ ...form, severity: e.target.value })}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              İptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
