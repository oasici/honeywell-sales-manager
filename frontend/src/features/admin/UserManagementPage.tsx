import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable } from '../../components/ui/DataTable';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { usersApi } from '../../lib/api';
import { translateUserRole } from '../../lib/labelTranslations';
import { formatDate } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

// Map role → Badge variant. Admin gets brand-tinted treatment so the
// privilege level is unambiguous at a glance.
type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'default';
const ROLE_TONE: Record<string, BadgeTone> = {
  admin: 'danger',
  sales_manager: 'warning',
  sales_rep: 'info',
  viewer: 'default',
};

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
        render: (row: User) => (
          <div className="flex items-center gap-3">
            <span
              aria-hidden
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-honeywell-red/10 text-[12px] font-semibold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20"
            >
              {(row.full_name || '?')
                .split(' ')
                .map((n) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold text-slate-900 dark:text-white">
                {row.full_name}
              </p>
              <p className="truncate text-[12px] text-slate-500 dark:text-slate-400">
                {row.email}
              </p>
            </div>
          </div>
        ),
      },
      {
        key: 'role',
        header: t('admin.col_role'),
        render: (row: User) => (
          <div className="flex items-center gap-2">
            <Badge variant={ROLE_TONE[row.role] ?? 'default'} size="sm" dot>
              {translateUserRole(row.role, t)}
            </Badge>
            <select
              value={row.role}
              onChange={(e) => handleRoleChange(row.id, e.target.value)}
              className="h-7 cursor-pointer rounded-[8px] border border-slate-200 bg-white px-2 text-[12px] font-medium text-slate-700 transition-colors hover:border-slate-300 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              aria-label={t('admin.aria_role_change').replace('{name}', row.full_name)}
            >
              {roleOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        ),
      },
      {
        key: 'is_active',
        header: t('admin.col_active'),
        align: 'center' as const,
        render: (row: User) => (
          <button
            type="button"
            role="switch"
            aria-checked={row.is_active}
            aria-label={`${row.full_name} ${row.is_active ? t('subscription.status_active') : t('admin.inactive')}`}
            onClick={() => handleToggleActive(row.id)}
            className={[
              'relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200',
              'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
              row.is_active
                ? 'bg-honeywell-red'
                : 'bg-slate-200 dark:bg-slate-700',
            ].join(' ')}
          >
            <span
              className={[
                'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-(--shadow-sm) ring-0 transition-transform duration-200',
                row.is_active ? 'translate-x-[22px]' : 'translate-x-0.5',
              ].join(' ')}
            />
          </button>
        ),
      },
      {
        key: 'created_at',
        header: t('admin.col_created'),
        sortable: true,
        render: (row: User) => (
          <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
            {formatDate(row.created_at)}
          </span>
        ),
      },
    ],
    [t, roleOptions, handleRoleChange, handleToggleActive],
  );

  const confirmRoleLabel = roleConfirm ? translateUserRole(roleConfirm.newRole, t) : '';

  return (
    <div>
      <PageHeader title={t('admin.users_title')} description={t('admin.users_description')} />

      {/* Search row — adornment icon makes the field instantly recognizable
          as "find a user" instead of a generic input. */}
      <div className="relative mb-4 max-w-md">
        <Search
          size={14}
          className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
          aria-hidden
        />
        <Input
          placeholder={t('admin.search_ph')}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="pl-9"
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
