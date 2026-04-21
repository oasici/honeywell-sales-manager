import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable } from '../../components/ui/DataTable';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { Input } from '../../components/ui/Input';
import { usersApi } from '../../lib/api';
import { translateUserRole } from '../../lib/labelTranslations';
import { formatDate } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

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

const PAGE_SIZE = 20;

export default function UserManagementPage() {
  const t = useT();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [roleConfirm, setRoleConfirm] = useState<{ userId: number; newRole: string } | null>(null);

  const roleOptions = useMemo(
    () => [
      { value: 'admin', label: t('admin.role_admin') },
      { value: 'sales_manager', label: t('admin.role_sales_manager') },
      { value: 'sales_rep', label: t('admin.role_sales_rep') },
      { value: 'viewer', label: t('admin.role_viewer') },
    ],
    [t],
  );

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
      toast.success(t('admin.toast_user_status').replace('{id}', String(id)));
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => toast.error(t('admin.toast_status_fail')),
  });

  const changeRoleMutation = useMutation({
    mutationFn: ({ id, role }: { id: number; role: string }) => usersApi.changeRole(id, role),
    onSuccess: () => {
      toast.success(t('admin.toast_role_ok'));
      setRoleConfirm(null);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => {
      toast.error(t('admin.toast_role_fail'));
      setRoleConfirm(null);
    },
  });

  const handleRoleChange = useCallback((userId: number, newRole: string) => {
    setRoleConfirm({ userId, newRole });
  }, []);

  function confirmRoleChange() {
    if (!roleConfirm) return;
    changeRoleMutation.mutate({ id: roleConfirm.userId, role: roleConfirm.newRole });
  }

  const handleToggleActive = useCallback(
    (userId: number) => {
      toggleActiveMutation.mutate(userId);
    },
    [toggleActiveMutation],
  );

  const users = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  const columns = useMemo(
    () => [
      {
        key: 'full_name',
        header: t('admin.col_name'),
        sortable: true,
        render: (row: User) => <span className="font-medium text-gray-900">{row.full_name}</span>,
      },
      {
        key: 'email',
        header: t('admin.col_email'),
        sortable: true,
      },
      {
        key: 'role',
        header: t('admin.col_role'),
        render: (row: User) => (
          <select
            value={row.role}
            onChange={(e) => handleRoleChange(row.id, e.target.value)}
            className="rounded-lg border border-gray-300 px-2 py-1 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light"
            aria-label={t('admin.aria_role_change').replace('{name}', row.full_name)}
          >
            {roleOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ),
      },
      {
        key: 'is_active',
        header: t('admin.col_active'),
        render: (row: User) => (
          <button
            type="button"
            role="switch"
            aria-checked={row.is_active}
            aria-label={`${row.full_name} ${row.is_active ? t('subscription.status_active') : t('admin.inactive')}`}
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
        header: t('admin.col_created'),
        sortable: true,
        render: (row: User) => (
          <span className="text-sm text-gray-500">{formatDate(row.created_at)}</span>
        ),
      },
    ],
    [t, roleOptions, handleRoleChange, handleToggleActive],
  );

  const confirmRoleLabel = roleConfirm ? translateUserRole(roleConfirm.newRole, t) : '';

  return (
    <div>
      <PageHeader title={t('admin.users_title')} description={t('admin.users_description')} />

      <div className="mb-6 max-w-md">
        <Input
          placeholder={t('admin.search_ph')}
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
        emptyMessage={t('admin.users_empty')}
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />

      <ConfirmDialog
        isOpen={roleConfirm !== null}
        onClose={() => setRoleConfirm(null)}
        onConfirm={confirmRoleChange}
        title={t('admin.confirm_role_title')}
        message={t('admin.confirm_role_msg').replace('{role}', confirmRoleLabel)}
        confirmLabel={t('admin.confirm_btn')}
        confirmVariant="primary"
        isLoading={changeRoleMutation.isPending}
      />
    </div>
  );
}
