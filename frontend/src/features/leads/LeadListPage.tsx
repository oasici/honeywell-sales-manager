import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { onLeadCreated } from '../../lib/cacheInvalidation';
import { PageHeader } from '../../components/ui/PageHeader';
import { SavedViewsBar } from '../../components/ui/SavedViewsBar';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
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
// Round-4 R4-TS-10 — use the canonical Lead type from lib/types.ts
// instead of the local copy that drifted away from the API shape.
import type { Lead } from '../../lib/types';

const STATUS_COLORS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  new: 'default',
  contacted: 'info',
  qualified: 'success',
  unqualified: 'danger',
  converted: 'success',
};

/**
 * ScoreBadge — color-coded lead-score chip with brand-tinted ring.
 *
 * Buckets: ≥70 = healthy (emerald), 40–69 = warm (amber), <40 = cold (red).
 * The 7×7 pill keeps the row compact while the tabular-nums numeral stays
 * aligned across rows.
 */
function ScoreBadge({ score }: { score: number }) {
  const tone =
    score >= 70
      ? 'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40'
      : score >= 40
        ? 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:ring-amber-900/40'
        : 'bg-red-50 text-red-700 ring-red-100 dark:bg-red-950/30 dark:text-red-400 dark:ring-red-900/40';
  return (
    <span
      className={[
        'inline-flex h-7 min-w-[36px] items-center justify-center rounded-full px-2 text-[12px] font-bold tabular-nums ring-1 ring-inset',
        tone,
      ].join(' ')}
      aria-label={`Skor ${score}`}
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
    // R5-FORM-1 — backend's LeadCreate already accepts notes, but the
    // SPA never surfaced the field. Added so reps can capture context
    // (lead-source rationale, intro call summary etc.) at create time.
    notes: '',
    source: 'manual',
  });

  // R14-FE-1 exempt: page already renders a bespoke red isError surface
  // with retry button inline (R11-FE-1). QueryErrorBanner would duplicate.
  const { data, isLoading, isError, error, refetch } = useQuery({
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
      // R7-CACHE-1 — pre-fix only invalidated ['leads']; the helper
      // also touches dashboard / cockpit / lead-analytics rollups.
      onLeadCreated(queryClient);
      setShowCreate(false);
      setForm({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        company: '',
        title: '',
        notes: '',
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
      // Round-15 Sprint 15g cohort 6 — bulk lead actions can change
      // status/owner across many rows; onLeadCreated covers the
      // analytics + dashboard + cockpit fan-out the inline pattern
      // missed (R7-CACHE-1 pattern reused).
      onLeadCreated(queryClient);
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
      width: '40px',
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
            className="h-4 w-4 cursor-pointer rounded-[4px] border-slate-300 text-honeywell-red focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800"
          />
        </label>
      ),
    },
    {
      key: 'full_name',
      header: t('leads.col_name'),
      render: (row: Lead) => (
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-honeywell-red/10 text-[12px] font-semibold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20"
          >
            {(row.first_name?.[0] ?? '').toUpperCase()}
            {(row.last_name?.[0] ?? '').toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-slate-900 dark:text-white">
              {row.first_name} {row.last_name}
            </p>
            <p className="truncate text-[12px] text-slate-500 dark:text-slate-400">
              {/* Title is fetched per-row but never rendered before
                  audit F-16. Falls back to company so the line is
                  never empty. */}
              {row.title || row.company || '—'}
            </p>
            {/* Converted-lead back-link — when the lead has been
                converted, surface a link to the resulting customer
                so reps can pivot without bouncing back to leads. */}
            {row.converted_at && row.converted_customer_id != null && (
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400">
                ✓ Müşteri #{row.converted_customer_id}
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'email',
      header: t('leads.col_email'),
      render: (row: Lead) => (
        <div className="flex flex-col">
          <span className="text-[13px] text-slate-700 dark:text-slate-200">{row.email}</span>
          {row.phone && (
            <a
              href={`tel:${row.phone}`}
              onClick={(e) => e.stopPropagation()}
              className="text-[11px] text-slate-500 hover:underline"
            >
              {row.phone}
            </a>
          )}
        </div>
      ),
    },
    {
      key: 'lead_score',
      header: t('leads.col_score'),
      align: 'center' as const,
      numeric: true,
      render: (row: Lead) => <ScoreBadge score={row.lead_score} />,
    },
    {
      key: 'status',
      header: t('leads.col_status'),
      render: (row: Lead) => (
        <Badge variant={STATUS_COLORS[row.status] || 'default'} size="sm" dot>
          {translateLeadStatus(row.status, t)}
        </Badge>
      ),
    },
    {
      key: 'source',
      header: t('leads.col_source'),
      render: (row: Lead) => (
        <span className="text-[12px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {row.source}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: t('leads.col_date'),
      render: (row: Lead) => (
        <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {formatDate(row.created_at)}
        </span>
      ),
    },
  ];

  const statusOptions = [
    { value: '', label: t('leads.all_statuses') },
    ...LEAD_STATUS_VALUES.map((k) => ({ value: k, label: translateLeadStatus(k, t) })),
  ];

  return (
    <div>
      <PageHeader title={t('leads.title')} description={t('leads.description')}>
        <Button onClick={() => setShowCreate(true)}>
          <UserPlus size={14} />
          {t('leads.new')}
        </Button>
      </PageHeader>

      {/* S-E saved views — universal across list pages */}
      <div className="mb-3">
        <SavedViewsBar
          route="/leads"
          queryJson={JSON.stringify({ search, statusFilter, page })}
          onApply={(view) => {
            try {
              const payload = JSON.parse(view.query_json) as {
                search?: string;
                statusFilter?: string;
                page?: number;
              };
              if (typeof payload.search === 'string') setSearch(payload.search);
              if (typeof payload.statusFilter === 'string') setStatusFilter(payload.statusFilter);
              if (typeof payload.page === 'number') setPage(payload.page);
            } catch {
              /* ignore malformed view */
            }
          }}
        />
      </div>

      {/* Filter row — search input gets a leading icon adornment so the
          intent is unmistakable. Status select sits beside it; "Tümünü
          seç" stays on the right so the eye lands on it after scanning. */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="relative min-w-[220px] flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
          <Input
            type="text"
            placeholder={t('leads.search_placeholder')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="pl-9"
          />
        </div>
        <div className="w-52">
          <Select
            options={statusOptions}
            value={statusFilter || ''}
            onChange={(e) => {
              setStatusFilter(e.target.value || undefined);
              setPage(1);
            }}
          />
        </div>
        {items.length > 0 && (
          <label className="ml-auto inline-flex h-11 cursor-pointer select-none items-center gap-2 text-[13px] text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={toggleAll}
              className="h-4 w-4 rounded-[4px] border-slate-300 text-honeywell-red focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800"
            />
            {t('leads.select_all')}
          </label>
        )}
      </div>

      {/* Round-11 R11-FE-1 — surface load failure. */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded-[8px] border border-(--danger)/30 bg-(--danger-bg) px-3 py-2 text-[13px] text-(--danger)">
          <span>{(error as Error | undefined)?.message ?? t('common.error_load_failed')}</span>
          <Button variant="ghost" onClick={() => refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      )}

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

      {/* Create Lead Modal — uses Modal's footer slot so action buttons
          stay pinned even if the form scrolls. */}
      <Modal
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        title={t('leads.modal_create_title')}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreate(false)} type="button">
              {t('common.cancel')}
            </Button>
            <Button type="submit" form="lead-create-form" loading={createMutation.isPending}>
              {t('common.create')}
            </Button>
          </>
        }
      >
        <form
          id="lead-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate(form);
          }}
          className="space-y-4"
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
          {/* R5-FORM-1 — surface the notes field so reps can capture
              free-text context at create time. Backend accepts it via
              LeadCreate.notes. */}
          <div>
            <label
              htmlFor="lead-notes"
              className="mb-1.5 block text-[12px] font-medium text-slate-700 dark:text-slate-300"
            >
              {t('leads.notes')}
            </label>
            <textarea
              id="lead-notes"
              rows={3}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder={t('leads.notes_ph')}
              className="block w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
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
        size="sm"
        description={t('leads.status_change_desc').replace('{count}', String(selectedCount))}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowStatusModal(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="primary"
              loading={bulkMutation.isPending}
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
          </>
        }
      >
        <Select
          label={t('leads.col_status')}
          options={LEAD_STATUS_VALUES.map((k) => ({
            value: k,
            label: translateLeadStatus(k, t),
          }))}
          value={newStatus}
          onChange={(e) => setNewStatus(e.target.value)}
        />
      </Modal>
    </div>
  );
}
