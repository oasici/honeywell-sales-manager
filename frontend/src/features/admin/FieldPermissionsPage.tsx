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
import { fieldPermissionsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { FieldPermission } from '../../lib/types';

const ROLE_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'sales_rep', label: 'Satış Temsilcisi' },
  { value: 'sales_manager', label: 'Satış Muduru' },
  { value: 'operations', label: 'Operasyon' },
];

const ROLE_CREATE_OPTIONS = [
  { value: 'sales_rep', label: 'Satış Temsilcisi' },
  { value: 'sales_manager', label: 'Satış Muduru' },
  { value: 'operations', label: 'Operasyon' },
];

const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'customer', label: 'Müşteri' },
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'email', label: 'E-posta' },
];

const ENTITY_TYPE_CREATE_OPTIONS = [
  { value: 'customer', label: 'Müşteri' },
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'email', label: 'E-posta' },
];

const ACCESS_LEVEL_OPTIONS = [
  { value: 'read', label: 'Okuma' },
  { value: 'write', label: 'Yazma' },
  { value: 'hidden', label: 'Gizli' },
  { value: 'masked', label: 'Maskeli' },
];

const ACCESS_VARIANT: Record<string, 'success' | 'info' | 'default' | 'warning'> = {
  read: 'info',
  write: 'success',
  hidden: 'default',
  masked: 'warning',
};

const INITIAL_FORM = {
  role: 'sales_rep',
  entity_type: 'customer',
  field_name: '',
  access_level: 'read',
};

export default function FieldPermissionsPage() {
  const queryClient = useQueryClient();

  const [roleFilter, setRoleFilter] = useState('');
  const [entityTypeFilter, setEntityTypeFilter] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [form, setForm] = useState(INITIAL_FORM);

  const filterParams: Record<string, string> = {};
  if (roleFilter) filterParams.role = roleFilter;
  if (entityTypeFilter) filterParams.entity_type = entityTypeFilter;

  const { data, isLoading } = useQuery<FieldPermission[]>({
    queryKey: ['fieldPermissions', filterParams],
    queryFn: () => fieldPermissionsApi.list(Object.keys(filterParams).length > 0 ? filterParams : undefined),
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => fieldPermissionsApi.create(payload),
    onSuccess: () => {
      toast.success('Alan izni oluşturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['fieldPermissions'] });
    },
    onError: () => toast.error('Alan izni oluşturulamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => fieldPermissionsApi.remove(id),
    onSuccess: () => {
      toast.success('Alan izni silindi');
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ['fieldPermissions'] });
    },
    onError: () => {
      toast.error('Alan izni silinemedi');
      setDeleteTarget(null);
    },
  });

  function handleCreate() {
    if (!form.field_name.trim()) {
      toast.error('Alan adi zorunludur');
      return;
    }
    createMutation.mutate(form);
  }

  const roleLabel = (role: string) =>
    ROLE_CREATE_OPTIONS.find((o) => o.value === role)?.label ?? role;

  const entityLabel = (entity: string) =>
    ENTITY_TYPE_CREATE_OPTIONS.find((o) => o.value === entity)?.label ?? entity;

  const accessLabel = (level: string) =>
    ACCESS_LEVEL_OPTIONS.find((o) => o.value === level)?.label ?? level;

  const permissions = data ?? [];

  const columns = [
    {
      key: 'role',
      header: 'Rol',
      sortable: true,
      render: (row: FieldPermission) => (
        <Badge variant="default" size="sm">{roleLabel(row.role)}</Badge>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlık Tipi',
      sortable: true,
      render: (row: FieldPermission) => (
        <span className="text-[13px] text-slate-700 dark:text-slate-200">
          {entityLabel(row.entity_type)}
        </span>
      ),
    },
    {
      key: 'field_name',
      header: 'Alan Adı',
      sortable: true,
      render: (row: FieldPermission) => (
        <span className="font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
          {row.field_name}
        </span>
      ),
    },
    {
      key: 'access_level',
      header: 'Erişim Seviyesi',
      render: (row: FieldPermission) => (
        <Badge variant={ACCESS_VARIANT[row.access_level] ?? 'default'} size="sm" dot>
          {accessLabel(row.access_level)}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      header: 'Oluşturulma',
      sortable: true,
      render: (row: FieldPermission) => (
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
      render: (row: FieldPermission) => (
        <Button size="sm" variant="ghost" onClick={() => setDeleteTarget(row.id)} aria-label="Sil">
          <Trash2 size={14} className="text-red-500" />
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Alan İzinleri"
        description="Rol bazında alan erişim izinlerini yönetin"
      >
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus size={14} />
          Yeni İzin
        </Button>
      </PageHeader>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="w-52">
          <Select
            label="Rol"
            options={ROLE_OPTIONS}
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          />
        </div>
        <div className="w-52">
          <Select
            label="Varlık Tipi"
            options={ENTITY_TYPE_OPTIONS}
            value={entityTypeFilter}
            onChange={(e) => setEntityTypeFilter(e.target.value)}
          />
        </div>
      </div>

      {isLoading && <Skeleton variant="table" />}

      {!isLoading && (
        <DataTable columns={columns} data={permissions} emptyMessage="Alan izni bulunamadı" />
      )}

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Alan İzni"
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
          <Select
            label="Rol"
            options={ROLE_CREATE_OPTIONS}
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
          <Select
            label="Varlık Tipi"
            options={ENTITY_TYPE_CREATE_OPTIONS}
            value={form.entity_type}
            onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
          />
          <Input
            label="Alan Adı"
            placeholder="Örneğin: email"
            value={form.field_name}
            onChange={(e) => setForm({ ...form, field_name: e.target.value })}
          />
          <Select
            label="Erişim Seviyesi"
            options={ACCESS_LEVEL_OPTIONS}
            value={form.access_level}
            onChange={(e) => setForm({ ...form, access_level: e.target.value })}
          />
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget !== null && deleteMutation.mutate(deleteTarget)}
        title="Alan Izni Sil"
        message="Bu alan iznini silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
