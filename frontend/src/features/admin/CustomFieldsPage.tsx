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
import { customFieldsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { CustomFieldDefinition } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'customer', label: 'Musteri' },
  { value: 'opportunity', label: 'Firsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'lead', label: 'Aday' },
];

const FIELD_TYPE_OPTIONS = [
  { value: 'text', label: 'Metin' },
  { value: 'number', label: 'Sayi' },
  { value: 'date', label: 'Tarih' },
  { value: 'select', label: 'Secim' },
  { value: 'checkbox', label: 'Onay Kutusu' },
];

const INITIAL_FORM = {
  field_name: '',
  field_type: 'text',
  options_json: '',
  is_required: false,
};

export default function CustomFieldsPage() {
  const queryClient = useQueryClient();

  const [entityType, setEntityType] = useState('customer');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [form, setForm] = useState(INITIAL_FORM);

  const { data, isLoading } = useQuery<{ items: CustomFieldDefinition[]; total: number }>({
    queryKey: ['customFields', entityType],
    queryFn: () => customFieldsApi.list(entityType),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => customFieldsApi.create(payload),
    onSuccess: () => {
      toast.success('Ozel alan olusturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['customFields', entityType] });
    },
    onError: () => toast.error('Ozel alan olusturulamadi'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => customFieldsApi.remove(id),
    onSuccess: () => {
      toast.success('Ozel alan silindi');
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ['customFields', entityType] });
    },
    onError: () => {
      toast.error('Ozel alan silinemedi');
      setDeleteTarget(null);
    },
  });

  function handleCreate() {
    if (!form.field_name.trim()) {
      toast.error('Alan adi zorunludur');
      return;
    }
    const payload: Record<string, unknown> = {
      entity_type: entityType,
      field_name: form.field_name,
      field_type: form.field_type,
      is_required: form.is_required,
    };
    if (form.field_type === 'select' && form.options_json.trim()) {
      payload.options_json = form.options_json;
    }
    createMutation.mutate(payload);
  }

  const items = data?.items ?? [];

  const columns = [
    {
      key: 'field_name',
      header: 'Alan Adi',
      sortable: true,
      render: (row: CustomFieldDefinition) => (
        <span className="font-medium text-gray-900">{row.field_name}</span>
      ),
    },
    {
      key: 'field_type',
      header: 'Tip',
      sortable: true,
      render: (row: CustomFieldDefinition) => {
        const label = FIELD_TYPE_OPTIONS.find((o) => o.value === row.field_type)?.label ?? row.field_type;
        return <Badge variant="info">{label}</Badge>;
      },
    },
    {
      key: 'is_required',
      header: 'Zorunlu',
      render: (row: CustomFieldDefinition) => (
        <Badge variant={row.is_required ? 'warning' : 'default'}>
          {row.is_required ? 'Evet' : 'Hayir'}
        </Badge>
      ),
    },
    {
      key: 'sort_order',
      header: 'Sira',
      sortable: true,
    },
    {
      key: 'created_at',
      header: 'Olusturulma',
      sortable: true,
      render: (row: CustomFieldDefinition) => (
        <span className="text-sm text-gray-500">
          {row.created_at ? formatDateTime(row.created_at) : '-'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Islemler',
      render: (row: CustomFieldDefinition) => (
        <Button size="sm" variant="danger" onClick={() => setDeleteTarget(row.id)}>
          Sil
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Ozel Alanlar"
        description="Varlik tipine gore ozel alan tanimlamalari"
      >
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Alan</Button>
      </PageHeader>

      {/* Entity type selector */}
      <div className="mb-6 max-w-xs">
        <Select
          label="Varlik Tipi"
          options={ENTITY_TYPE_OPTIONS}
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        />
      </div>

      {isLoading && <Skeleton variant="table" />}

      {!isLoading && (
        <DataTable
          columns={columns}
          data={items}
          emptyMessage="Ozel alan bulunamadi"
        />
      )}

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Ozel Alan"
      >
        <div className="space-y-4">
          <Input
            label="Alan Adi"
            placeholder="Ornegin: vergi_no"
            value={form.field_name}
            onChange={(e) => setForm({ ...form, field_name: e.target.value })}
          />
          <Select
            label="Alan Tipi"
            options={FIELD_TYPE_OPTIONS}
            value={form.field_type}
            onChange={(e) => setForm({ ...form, field_type: e.target.value })}
          />
          {form.field_type === 'select' && (
            <Input
              label="Secenekler (JSON)"
              placeholder='["Secenek 1", "Secenek 2"]'
              value={form.options_json}
              onChange={(e) => setForm({ ...form, options_json: e.target.value })}
            />
          )}
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_required}
              onChange={(e) => setForm({ ...form, is_required: e.target.checked })}
              className="rounded border-gray-300"
            />
            Zorunlu Alan
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              Iptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Olustur
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget !== null && deleteMutation.mutate(deleteTarget)}
        title="Ozel Alan Sil"
        message="Bu ozel alani silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
