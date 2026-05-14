import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { DataTable } from '../../components/ui/DataTable';
import { Badge } from '../../components/ui/Badge';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { complianceApi } from '../../lib/api';
import { onComplianceChanged } from '../../lib/cacheInvalidation';
import { formatDateTime } from '../../lib/formatters';

import type { RetentionPolicy } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'customer', label: 'Müşteri' },
  { value: 'email', label: 'E-posta' },
  { value: 'quote', label: 'Teklif' },
  { value: 'activity_log', label: 'Aktivite Loglari' },
];

const ACTION_OPTIONS = [
  { value: 'anonymize', label: 'Anonimlesitir' },
  { value: 'archive', label: 'Arsivle' },
  { value: 'notify', label: 'Bildir' },
];

const INITIAL_FORM = {
  entity_type: 'customer',
  retention_days: 365,
  action: 'anonymize',
  is_active: true,
};

export default function RetentionPoliciesPage() {
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [form, setForm] = useState(INITIAL_FORM);

  // R5-API-8 — backend canonicalized to {items, total, ...}; legacy
  // ``policies`` retained server-side as additive bridge.
  const { data, isLoading } = useQuery<{
    items?: RetentionPolicy[];
    policies?: RetentionPolicy[];
  }>({
    queryKey: ['compliance', 'retentionPolicies'],
    queryFn: () => complianceApi.listRetentionPolicies(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => complianceApi.createRetentionPolicy(payload),
    onSuccess: () => {
      toast.success('Saklama politikasi oluşturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      onComplianceChanged(queryClient);
    },
    onError: () => toast.error('Politika oluşturulamadı'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: typeof form }) =>
      complianceApi.updateRetentionPolicy(id, payload),
    onSuccess: () => {
      toast.success('Politika guncellendi');
      setEditingId(null);
      setForm(INITIAL_FORM);
      onComplianceChanged(queryClient);
    },
    onError: () => toast.error('Politika guncellenemedi'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => complianceApi.deleteRetentionPolicy(id),
    onSuccess: () => {
      toast.success('Politika silindi');
      setDeleteTarget(null);
      onComplianceChanged(queryClient);
    },
    onError: () => {
      toast.error('Politika silinemedi');
      setDeleteTarget(null);
    },
  });

  function handleOpenEdit(policy: RetentionPolicy) {
    setForm({
      entity_type: policy.entity_type,
      retention_days: policy.retention_days,
      action: policy.action,
      is_active: policy.is_active,
    });
    setEditingId(policy.id);
  }

  function handleSubmitEdit() {
    if (editingId === null) return;
    updateMutation.mutate({ id: editingId, payload: form });
  }

  function handleSubmitCreate() {
    createMutation.mutate(form);
  }

  // Round-5 Phase 7 — backend canonicalized to ``items``; legacy
  // ``policies`` retained server-side as additive bridge.
  const policies = data?.items ?? data?.policies ?? [];

  const columns = [
    {
      key: 'entity_type',
      header: 'Varlık Tipi',
      sortable: true,
      render: (row: RetentionPolicy) => {
        if (editingId === row.id) {
          return (
            <Select
              options={ENTITY_TYPE_OPTIONS}
              value={form.entity_type}
              onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
            />
          );
        }
        const label = ENTITY_TYPE_OPTIONS.find((o) => o.value === row.entity_type)?.label ?? row.entity_type;
        return <span>{label}</span>;
      },
    },
    {
      key: 'retention_days',
      header: 'Saklama (Gun)',
      sortable: true,
      render: (row: RetentionPolicy) => {
        if (editingId === row.id) {
          return (
            <Input
              type="number"
              value={String(form.retention_days)}
              onChange={(e) => setForm({ ...form, retention_days: parseInt(e.target.value, 10) || 0 })}
            />
          );
        }
        return <span>{row.retention_days}</span>;
      },
    },
    {
      key: 'action',
      header: 'Aksiyon',
      render: (row: RetentionPolicy) => {
        if (editingId === row.id) {
          return (
            <Select
              options={ACTION_OPTIONS}
              value={form.action}
              onChange={(e) => setForm({ ...form, action: e.target.value })}
            />
          );
        }
        const label = ACTION_OPTIONS.find((o) => o.value === row.action)?.label ?? row.action;
        return <Badge variant="info">{label}</Badge>;
      },
    },
    {
      key: 'is_active',
      header: 'Durum',
      render: (row: RetentionPolicy) => {
        if (editingId === row.id) {
          return (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                className="rounded border-slate-200"
              />
              Aktif
            </label>
          );
        }
        return (
          <Badge variant={row.is_active ? 'success' : 'default'}>
            {row.is_active ? 'Aktif' : 'Pasif'}
          </Badge>
        );
      },
    },
    {
      key: 'created_at',
      header: 'Olusturulma',
      sortable: true,
      render: (row: RetentionPolicy) => (
        <span className="text-sm text-slate-500">
          {row.created_at ? formatDateTime(row.created_at) : '-'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'İşlemler',
      render: (row: RetentionPolicy) => {
        if (editingId === row.id) {
          return (
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSubmitEdit} loading={updateMutation.isPending}>
                Kaydet
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditingId(null);
                  setForm(INITIAL_FORM);
                }}
              >
                İptal
              </Button>
            </div>
          );
        }
        return (
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={() => handleOpenEdit(row)}>
              Düzenle
            </Button>
            <Button size="sm" variant="danger" onClick={() => setDeleteTarget(row.id)}>
              Sil
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Saklama Politikalari"
        description="Veri saklama süresi politikalarini yonetin"
      >
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Politika</Button>
      </PageHeader>

      {isLoading && <Skeleton variant="table" />}

      {!isLoading && (
        <DataTable
          columns={columns}
          data={policies}
          emptyMessage="Saklama politikasi bulunamadi"
        />
      )}

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Saklama Politikasi"
      >
        <div className="space-y-4">
          <Select
            label="Varlık Tipi"
            options={ENTITY_TYPE_OPTIONS}
            value={form.entity_type}
            onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
          />
          <Input
            label="Saklama Süresi (Gun)"
            type="number"
            value={String(form.retention_days)}
            onChange={(e) => setForm({ ...form, retention_days: parseInt(e.target.value, 10) || 0 })}
          />
          <Select
            label="Aksiyon"
            options={ACTION_OPTIONS}
            value={form.action}
            onChange={(e) => setForm({ ...form, action: e.target.value })}
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="rounded border-slate-200"
            />
            Aktif
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              İptal
            </Button>
            <Button onClick={handleSubmitCreate} loading={createMutation.isPending}>
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget !== null && deleteMutation.mutate(deleteTarget)}
        title="Politika Sil"
        message="Bu saklama politikasini silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
