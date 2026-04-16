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
import { fieldPermissionsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { FieldPermission } from '../../lib/types';

const ROLE_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'sales_rep', label: 'Satis Temsilcisi' },
  { value: 'sales_manager', label: 'Satis Muduru' },
  { value: 'operations', label: 'Operasyon' },
];

const ROLE_CREATE_OPTIONS = [
  { value: 'sales_rep', label: 'Satis Temsilcisi' },
  { value: 'sales_manager', label: 'Satis Muduru' },
  { value: 'operations', label: 'Operasyon' },
];

const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'customer', label: 'Musteri' },
  { value: 'opportunity', label: 'Firsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'email', label: 'E-posta' },
];

const ENTITY_TYPE_CREATE_OPTIONS = [
  { value: 'customer', label: 'Musteri' },
  { value: 'opportunity', label: 'Firsat' },
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
      toast.success('Alan izni olusturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['fieldPermissions'] });
    },
    onError: () => toast.error('Alan izni olusturulamadi'),
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
        <span className="font-medium text-gray-900">{roleLabel(row.role)}</span>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlik Tipi',
      sortable: true,
      render: (row: FieldPermission) => <span>{entityLabel(row.entity_type)}</span>,
    },
    {
      key: 'field_name',
      header: 'Alan Adi',
      sortable: true,
    },
    {
      key: 'access_level',
      header: 'Erisim Seviyesi',
      render: (row: FieldPermission) => (
        <Badge variant={ACCESS_VARIANT[row.access_level] ?? 'default'}>
          {accessLabel(row.access_level)}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      header: 'Olusturulma',
      sortable: true,
      render: (row: FieldPermission) => (
        <span className="text-sm text-gray-500">
          {row.created_at ? formatDateTime(row.created_at) : '-'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Islemler',
      render: (row: FieldPermission) => (
        <Button size="sm" variant="danger" onClick={() => setDeleteTarget(row.id)}>
          Sil
        </Button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Alan Izinleri"
        description="Rol bazinda alan erisim izinlerini yonetin"
      >
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Izin</Button>
      </PageHeader>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-4">
        <div className="w-48">
          <Select
            label="Rol"
            options={ROLE_OPTIONS}
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          />
        </div>
        <div className="w-48">
          <Select
            label="Varlik Tipi"
            options={ENTITY_TYPE_OPTIONS}
            value={entityTypeFilter}
            onChange={(e) => setEntityTypeFilter(e.target.value)}
          />
        </div>
      </div>

      {isLoading && <Skeleton variant="table" />}

      {!isLoading && (
        <DataTable
          columns={columns}
          data={permissions}
          emptyMessage="Alan izni bulunamadi"
        />
      )}

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Alan Izni"
      >
        <div className="space-y-4">
          <Select
            label="Rol"
            options={ROLE_CREATE_OPTIONS}
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
          <Select
            label="Varlik Tipi"
            options={ENTITY_TYPE_CREATE_OPTIONS}
            value={form.entity_type}
            onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
          />
          <Input
            label="Alan Adi"
            placeholder="Ornegin: email"
            value={form.field_name}
            onChange={(e) => setForm({ ...form, field_name: e.target.value })}
          />
          <Select
            label="Erisim Seviyesi"
            options={ACCESS_LEVEL_OPTIONS}
            value={form.access_level}
            onChange={(e) => setForm({ ...form, access_level: e.target.value })}
          />
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
        title="Alan Izni Sil"
        message="Bu alan iznini silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
