import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable } from '../../components/ui/DataTable';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { Input } from '../../components/ui/Input';
import { usersApi } from '../../lib/api';
import { ROLE_LABELS } from '../../lib/constants';
import { formatDate } from '../../lib/formatters';

interface User {
  id: number;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface PaginatedUsers {
  items: User[];
  total: number;
  page: number;
  pages: number;
}

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Yonetici' },
  { value: 'sales_manager', label: 'Satış Muduru' },
  { value: 'sales_rep', label: 'Satış Temsilcisi' },
  { value: 'viewer', label: 'Goruntuleyici' },
];

const PAGE_SIZE = 20;

export default function UserManagementPage() {
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [roleConfirm, setRoleConfirm] = useState<{ userId: number; newRole: string } | null>(null);

  const { data, isLoading } = useQuery<PaginatedUsers>({
    queryKey: ['users', { page, search }],
    queryFn: () =>
      usersApi.getUsers({
        page,
        page_size: PAGE_SIZE,
        ...(search && { search }),
      }),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (id: number) => usersApi.toggleActive(id),
    onSuccess: (_data, id) => {
      toast.success(`Kullanıcı #${id} durumu guncellendi`);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => toast.error('Durum guncellenemedi'),
  });

  const changeRoleMutation = useMutation({
    mutationFn: ({ id, role }: { id: number; role: string }) => usersApi.changeRole(id, role),
    onSuccess: () => {
      toast.success('Rol başarıyla degistirildi');
      setRoleConfirm(null);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => {
      toast.error('Rol degistirilemedi');
      setRoleConfirm(null);
    },
  });

  function handleRoleChange(userId: number, newRole: string) {
    setRoleConfirm({ userId, newRole });
  }

  function confirmRoleChange() {
    if (!roleConfirm) return;
    changeRoleMutation.mutate({ id: roleConfirm.userId, role: roleConfirm.newRole });
  }

  function handleToggleActive(userId: number) {
    toggleActiveMutation.mutate(userId);
  }

  const users = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  const columns = [
    {
      key: 'full_name',
      header: 'İsim',
      sortable: true,
      render: (row: User) => (
        <span className="font-medium text-gray-900">{row.full_name}</span>
      ),
    },
    {
      key: 'email',
      header: 'Email',
      sortable: true,
    },
    {
      key: 'role',
      header: 'Rol',
      render: (row: User) => (
        <select
          value={row.role}
          onChange={(e) => handleRoleChange(row.id, e.target.value)}
          className="rounded-lg border border-gray-300 px-2 py-1 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light"
          aria-label={`${row.full_name} için rol degistir`}
        >
          {ROLE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      ),
    },
    {
      key: 'is_active',
      header: 'Aktif',
      render: (row: User) => (
        <button
          type="button"
          role="switch"
          aria-checked={row.is_active}
          aria-label={`${row.full_name} ${row.is_active ? 'aktif' : 'pasif'}`}
          onClick={() => handleToggleActive(row.id)}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-honeywell-red focus-visible:ring-offset-2 ${
            row.is_active ? 'bg-green-500' : 'bg-gray-300'
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ${
              row.is_active ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      ),
    },
    {
      key: 'created_at',
      header: 'Olusturulma',
      sortable: true,
      render: (row: User) => (
        <span className="text-sm text-gray-500">{formatDate(row.created_at)}</span>
      ),
    },
  ];

  const confirmRoleLabel = roleConfirm
    ? ROLE_LABELS[roleConfirm.newRole] || roleConfirm.newRole
    : '';

  return (
    <div>
      <PageHeader
        title="Kullanıcı Yönetimi"
        description="Sistem kullanicilarini yonetin"
      />

      <div className="mb-6 max-w-md">
        <Input
          placeholder="İsim veya email ile ara..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
      </div>

      <DataTable
        columns={columns}
        data={users}
        loading={isLoading}
        emptyMessage="Kullanıcı bulunamadi"
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />

      <ConfirmDialog
        isOpen={roleConfirm !== null}
        onClose={() => setRoleConfirm(null)}
        onConfirm={confirmRoleChange}
        title="Rol Degistir"
        message={`Bu kullanicinin rolunu "${confirmRoleLabel}" olarak degistirmek istediginizden emin misiniz?`}
        confirmLabel="Degistir"
        confirmVariant="primary"
        isLoading={changeRoleMutation.isPending}
      />
    </div>
  );
}
