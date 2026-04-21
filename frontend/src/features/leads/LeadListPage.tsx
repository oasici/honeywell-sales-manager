import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { BulkActionBar } from '../../components/ui/BulkActionBar';
import { useMultiSelect } from '../../hooks/useMultiSelect';
import { leadsApi } from '../../lib/api';
import { getErrorMessage } from '../../lib/utils';
import { DuplicateWarning } from '../../components/ui/DuplicateWarning';
import { formatDate } from '../../lib/formatters';
import { UserPlus, Search } from 'lucide-react';
import { useT } from '../../hooks/useT';
import { LEAD_STATUS_VALUES, translateLeadStatus } from '../../lib/labelTranslations';

interface Lead {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  company?: string;
  title?: string;
  source: string;
  status: string;
  lead_score: number;
  created_at: string;
}

const STATUS_COLORS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  new: 'default',
  contacted: 'info',
  qualified: 'success',
  unqualified: 'danger',
  converted: 'success',
};

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70
      ? 'text-green-600 bg-green-50 dark:bg-green-900/20 dark:text-green-400'
      : score >= 40
        ? 'text-amber-600 bg-amber-50 dark:bg-amber-900/20 dark:text-amber-400'
        : 'text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-bold ${color}`}
    >
      {score}
    </span>
  );
}

export default function LeadListPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [showCreate, setShowCreate] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [newStatus, setNewStatus] = useState('new');
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    company: '',
    title: '',
    source: 'manual',
  });

  const { data, isLoading } = useQuery({
    queryKey: ['leads', page, search, statusFilter],
    queryFn: () =>
      leadsApi.list({ page, page_size: 20, q: search || undefined, status: statusFilter }),
  });

  const items = data?.items || [];

  const {
    selectedIds,
    toggleItem,
    toggleAll,
    isSelected,
    clearSelection,
    isAllSelected,
    selectedCount,
  } = useMultiSelect(items);

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => leadsApi.create(payload),
    onSuccess: () => {
      toast.success(t('leads.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['leads'] });
      setShowCreate(false);
      setForm({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        company: '',
        title: '',
        source: 'manual',
      });
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, t('leads.error_generic'))),
  });

  const bulkMutation = useMutation({
    mutationFn: (payload: { ids: number[]; action: string; params?: Record<string, unknown> }) =>
      leadsApi.bulkAction(payload),
    onSuccess: (res) => {
      toast.success(res.message);
      clearSelection();
      queryClient.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: () => toast.error(t('leads.bulk_failed')),
  });

  const handleBulkAction = useCallback(
    (key: string) => {
      const ids = Array.from(selectedIds);
      if (key === 'delete') {
        setShowDeleteConfirm(true);
        return;
      }
      if (key === 'export') {
        bulkMutation.mutate({ ids, action: 'export' });
        return;
      }
      if (key === 'assign') {
        const ownerIdStr = window.prompt(t('leads.prompt_assign_user_id'));
        if (!ownerIdStr) return;
        const ownerId = parseInt(ownerIdStr, 10);
        if (isNaN(ownerId)) {
          toast.error(t('leads.invalid_user_id'));
          return;
        }
        bulkMutation.mutate({ ids, action: 'assign', params: { owner_id: ownerId } });
        return;
      }
      if (key === 'change_status') {
        setShowStatusModal(true);
        return;
      }
    },
    [selectedIds, bulkMutation],
  );

  const BULK_ACTIONS = [
    { key: 'change_status', label: t('leads.bulk_change_status') },
    { key: 'assign', label: t('leads.bulk_assign') },
    { key: 'export', label: t('leads.bulk_export') },
    { key: 'delete', label: t('leads.bulk_delete'), variant: 'danger' as const },
  ];

  const columns = [
    {
      key: 'select',
      header: '',
      render: (row: Lead) => (
        <label
          className="flex items-center"
          aria-label={`${row.first_name} ${row.last_name} ${t('leads.aria_select_row_suffix')}`}
        >
          <input
            type="checkbox"
            checked={isSelected(row.id)}
            onChange={(e) => {
              e.stopPropagation();
              toggleItem(row.id);
            }}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
        </label>
      ),
    },
    {
      key: 'full_name',
      header: t('leads.col_name'),
      render: (row: Lead) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-white">
            {row.first_name} {row.last_name}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{row.company || '-'}</p>
        </div>
      ),
    },
    { key: 'email', header: t('leads.col_email') },
    {
      key: 'lead_score',
      header: t('leads.col_score'),
      render: (row: Lead) => <ScoreBadge score={row.lead_score} />,
    },
    {
      key: 'status',
      header: t('leads.col_status'),
      render: (row: Lead) => (
        <Badge variant={STATUS_COLORS[row.status] || 'default'}>
          {translateLeadStatus(row.status, t)}
        </Badge>
      ),
    },
    { key: 'source', header: t('leads.col_source') },
    {
      key: 'created_at',
      header: t('leads.col_date'),
      render: (row: Lead) => formatDate(row.created_at),
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title={t('leads.title')} description={t('leads.description')}>
        <Button onClick={() => setShowCreate(true)}>
          <UserPlus className="mr-1 h-4 w-4" /> {t('leads.new')}
        </Button>
      </PageHeader>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder={t('leads.search_placeholder')}
            className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-10 pr-4 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <select
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
          value={statusFilter || ''}
          onChange={(e) => {
            setStatusFilter(e.target.value || undefined);
            setPage(1);
          }}
        >
          <option value="">{t('leads.all_statuses')}</option>
          {LEAD_STATUS_VALUES.map((k) => (
            <option key={k} value={k}>
              {translateLeadStatus(k, t)}
            </option>
          ))}
        </select>
        {items.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={toggleAll}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            {t('leads.select_all')}
          </label>
        )}
      </div>

      <Card>
        <DataTable
          columns={columns}
          data={items}
          loading={isLoading}
          emptyMessage={t('leads.empty')}
          onRowClick={(row: Lead) => navigate(`/leads/${row.id}`)}
          page={page}
          totalPages={data?.pages || 0}
          onPageChange={setPage}
        />
      </Card>

      {/* Create Lead Modal */}
      <Modal
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        title={t('leads.modal_create_title')}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate(form);
          }}
          className="space-y-3"
        >
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('leads.first_name')}
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              required
            />
            <Input
              label={t('leads.last_name')}
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
              required
            />
          </div>
          <Input
            label={t('leads.col_email')}
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
          <Input
            label={t('leads.phone')}
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <Input
            label={t('leads.company')}
            value={form.company}
            onChange={(e) => setForm({ ...form, company: e.target.value })}
          />
          <DuplicateWarning
            entityType="lead"
            name={`${form.first_name} ${form.last_name}`.trim()}
            company={form.company}
            email={form.email}
          />
          <Input
            label={t('leads.job_title')}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowCreate(false)} type="button">
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              {t('common.create')}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Bulk Action Bar */}
      <BulkActionBar
        selectedCount={selectedCount}
        actions={BULK_ACTIONS}
        onAction={handleBulkAction}
        onClearSelection={clearSelection}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => {
          bulkMutation.mutate({ ids: Array.from(selectedIds), action: 'delete' });
          setShowDeleteConfirm(false);
        }}
        title={t('leads.delete_title')}
        message={t('leads.delete_message').replace('{count}', String(selectedCount))}
        confirmLabel={t('common.delete')}
        confirmVariant="danger"
        isLoading={bulkMutation.isPending}
      />

      {/* Status Change Modal */}
      <Modal
        isOpen={showStatusModal}
        onClose={() => setShowStatusModal(false)}
        title={t('leads.status_change_title')}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            {t('leads.status_change_desc').replace('{count}', String(selectedCount))}
          </p>
          <select
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
            value={newStatus}
            onChange={(e) => setNewStatus(e.target.value)}
          >
            {LEAD_STATUS_VALUES.map((k) => (
              <option key={k} value={k}>
                {translateLeadStatus(k, t)}
              </option>
            ))}
          </select>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowStatusModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => {
                bulkMutation.mutate({
                  ids: Array.from(selectedIds),
                  action: 'change_status',
                  params: { status: newStatus },
                });
                setShowStatusModal(false);
              }}
            >
              {t('leads.apply')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
