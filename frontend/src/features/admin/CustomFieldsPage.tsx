import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { DataTable } from '../../components/ui/DataTable';
import { Badge } from '../../components/ui/Badge';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { customFieldsApi } from '../../lib/api';
import { onCustomFieldChanged } from '../../lib/cacheInvalidation';
import { formatDateTime } from '../../lib/formatters';

import type { CustomFieldDefinition } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'customer', label: 'Müşteri' },
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'lead', label: 'Aday' },
];

const FIELD_TYPE_OPTIONS = [
  { value: 'text', label: 'Metin' },
  { value: 'number', label: 'Sayi' },
  { value: 'date', label: 'Tarih' },
  { value: 'select', label: 'Seçim' },
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

  const { data, isLoading, isError, refetch } = useQuery<{
    items: CustomFieldDefinition[];
    total: number;
  }>({
    queryKey: ['customFields', entityType],
    queryFn: () => customFieldsApi.list(entityType),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => customFieldsApi.create(payload),
    onSuccess: () => {
      toast.success('Özel alan oluşturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      onCustomFieldChanged(queryClient, entityType);
    },
    onError: () => toast.error('Özel alan oluşturulamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => customFieldsApi.remove(id),
    onSuccess: () => {
      toast.success('Özel alan silindi');
      setDeleteTarget(null);
      onCustomFieldChanged(queryClient, entityType);
    },
    onError: () => {
      toast.error('Özel alan silinemedi');
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
      header: 'Alan Adı',
      sortable: true,
      render: (row: CustomFieldDefinition) => (
        <span className="font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
          {row.field_name}
        </span>
      ),
    },
    {
      key: 'field_type',
      header: 'Tip',
      sortable: true,
      render: (row: CustomFieldDefinition) => {
        const label =
          FIELD_TYPE_OPTIONS.find((o) => o.value === row.field_type)?.label ?? row.field_type;
        // For select-type fields, surface the configured choices as
        // chips — pre audit F-21 the admin couldn't see them without
        // re-creating the field.
        let options: string[] = [];
        if (row.field_type === 'select' && row.options_json) {
          try {
            const parsed = JSON.parse(row.options_json) as unknown;
            if (Array.isArray(parsed)) {
              options = parsed
                .map((o) =>
                  typeof o === 'string'
                    ? o
                    : typeof o === 'object' && o !== null && 'label' in o
                      ? String((o as { label: unknown }).label)
                      : null,
                )
                .filter((s): s is string => Boolean(s));
            }
          } catch {
            options = [];
          }
        }
        return (
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="info" size="sm">
              {label}
            </Badge>
            {options.slice(0, 4).map((opt, i) => (
              <span
                key={i}
                className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                {opt}
              </span>
            ))}
            {options.length > 4 && (
              <span className="text-[10px] text-slate-500">+{options.length - 4}</span>
            )}
          </div>
        );
      },
    },
    {
      key: 'is_required',
      header: 'Zorunlu',
      align: 'center' as const,
      render: (row: CustomFieldDefinition) => (
        <Badge variant={row.is_required ? 'warning' : 'default'} size="sm" dot>
          {row.is_required ? 'Evet' : 'Hayır'}
        </Badge>
      ),
    },
    {
      key: 'sort_order',
      header: 'Sıra',
      sortable: true,
      align: 'right' as const,
      numeric: true,
      render: (row: CustomFieldDefinition) => (
        <span className="text-[13px] tabular-nums text-slate-700 dark:text-slate-300">
          {row.sort_order}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Oluşturulma',
      sortable: true,
      render: (row: CustomFieldDefinition) => (
        <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {row.created_at ? formatDateTime(row.created_at) : '—'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right' as const,
      width: '80px',
      render: (row: CustomFieldDefinition) => (
        <Button size="sm" variant="ghost" onClick={() => setDeleteTarget(row.id)} aria-label="Sil">
          <Trash2 size={14} className="text-red-500" />
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Özel Alanlar" description="Varlık tipine göre özel alan tanımlamaları">
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus size={14} />
          Yeni Alan
        </Button>
      </PageHeader>

      {/* Entity type selector */}
      <div className="mb-6 max-w-xs">
        <Select
          label="Varlık Tipi"
          options={ENTITY_TYPE_OPTIONS}
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        />
      </div>

      {isError ? (
        <QueryErrorBanner variant="block" onRetry={() => refetch()} />
      ) : isLoading ? (
        <Skeleton variant="table" />
      ) : (
        <DataTable columns={columns} data={items} emptyMessage="Özel alan bulunamadı" />
      )}

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Özel Alan"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              İptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Oluştur
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Alan Adı"
            placeholder="Örneğin: vergi_no"
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
              label="Seçenekler (JSON)"
              placeholder='["Seçenek 1", "Seçenek 2"]'
              value={form.options_json}
              onChange={(e) => setForm({ ...form, options_json: e.target.value })}
            />
          )}
          <label className="flex cursor-pointer select-none items-center gap-2.5 rounded-[10px] border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-[13px] text-slate-700 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
            <input
              type="checkbox"
              checked={form.is_required}
              onChange={(e) => setForm({ ...form, is_required: e.target.checked })}
              className="h-4 w-4 cursor-pointer rounded-[4px] border-slate-300 text-honeywell-red focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800"
            />
            Zorunlu Alan
          </label>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget !== null && deleteMutation.mutate(deleteTarget)}
        title="Özel Alan Sil"
        message="Bu özel alani silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
