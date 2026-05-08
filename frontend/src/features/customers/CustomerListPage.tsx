import { useState, useRef, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ChevronDown, ExternalLink, FileText, Sparkles, TrendingUp, Users } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { SavedViewsBar } from '../../components/ui/SavedViewsBar';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { BulkActionBar } from '../../components/ui/BulkActionBar';
import { useMultiSelect } from '../../hooks/useMultiSelect';
import { customersApi, quotesApi } from '../../lib/api';
import { onCustomerCreated } from '../../lib/cacheInvalidation';
import { DuplicateWarning } from '../../components/ui/DuplicateWarning';
import { formatCurrency } from '../../lib/formatters';
import { STATUS_COLORS } from '../../lib/constants';
import { translateStatus } from '../../lib/labelTranslations';
import { useT } from '../../hooks/useT';
import type { Customer, Quote, PaginatedResponse } from '../../lib/types';

/* ── Avatar color palette ── */
const AVATAR_COLORS = [
  'bg-rose-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-sky-500',
  'bg-violet-500',
  'bg-pink-500',
  'bg-teal-500',
  'bg-indigo-500',
  'bg-orange-500',
  'bg-cyan-500',
];

function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % AVATAR_COLORS.length;
  return AVATAR_COLORS[index];
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

/* ── Customer Card with Quote Dropdown ── */
function CustomerCard({
  customer: c,
  navigate,
  isSelected,
  onToggle,
}: {
  customer: Customer;
  navigate: ReturnType<typeof useNavigate>;
  isSelected: boolean;
  onToggle: (id: number) => void;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const quoteCount = c.quote_count ?? 0;

  const avatarColor = useMemo(() => getAvatarColor(c.name), [c.name]);
  const initials = useMemo(() => getInitials(c.name), [c.name]);

  const { data: quotesData, isLoading: quotesLoading } = useQuery<PaginatedResponse<Quote>>({
    queryKey: ['customer-quotes-card', c.id],
    queryFn: () => quotesApi.getQuotes({ customer_id: c.id, page_size: 20 }),
    enabled: expanded && quoteCount > 0,
  });

  const quotes = quotesData?.items ?? [];

  // Linear/Stripe-style customer card: smaller avatar with ring instead of
  // shadow, cleaner typography hierarchy (name 15/600, company 13/500 muted,
  // email 12/400 even more muted), tighter stats row with overline labels.
  return (
    <div
      className={[
        'card-modern flex flex-col transition-shadow duration-150',
        'hover:shadow-sm',
        isSelected ? 'ring-2 ring-honeywell-red/60 ring-offset-2 ring-offset-slate-50' : '',
      ].join(' ')}
    >
      {/* Top section - clickable to customer detail */}
      <div className="flex items-start gap-3 p-5">
        {/* Checkbox */}
        <label
          className="flex items-center shrink-0 pt-0.5"
          aria-label={`${c.name} ${t('customers.select_row_suffix')}`}
        >
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onToggle(c.id)}
            className="h-4 w-4 rounded border-slate-300 text-honeywell-red focus:ring-honeywell-red/30"
          />
        </label>

        <button
          type="button"
          onClick={() => navigate(`/customers/${c.id}`)}
          className="flex items-start gap-3 flex-1 text-left transition-colors rounded-lg -m-1 p-1 hover:bg-slate-50"
        >
          {/* Avatar — smaller (40px) with subtle ring instead of drop shadow */}
          <div
            className={`${avatarColor} flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold text-white ring-2 ring-white`}
          >
            {initials}
          </div>

          {/* Info */}
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-[15px] font-semibold leading-tight text-slate-900">
              {c.name}
            </h3>
            {c.company && <p className="mt-0.5 truncate text-[13px] text-slate-500">{c.company}</p>}
            <p className="mt-0.5 truncate text-xs text-slate-400">{c.email}</p>
            {/* Enrichment metadata — surfaces industry + an "AI" badge
                when the customer has been auto-enriched (audit F-2). */}
            {(c.industry || c.enriched_at) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                {c.industry && (
                  <span className="inline-flex items-center rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                    {c.industry}
                  </span>
                )}
                {c.employee_count != null && (
                  <span className="text-[10px] text-slate-400">
                    {c.employee_count.toLocaleString()} {t('customers.employees_suffix')}
                  </span>
                )}
                {c.enriched_at && (
                  <span
                    title={t('customers.enriched_tooltip')}
                    className="inline-flex items-center gap-0.5 rounded-full bg-purple-50 px-1.5 py-0.5 text-[10px] font-medium text-purple-700"
                  >
                    <Sparkles size={10} />
                    AI
                  </span>
                )}
              </div>
            )}
          </div>
        </button>
      </div>

      {/* Stats row + dropdown toggle */}
      <div className="border-t border-slate-100">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (quoteCount > 0) setExpanded(!expanded);
          }}
          className={[
            'flex w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors',
            quoteCount > 0 ? 'hover:bg-slate-50 cursor-pointer' : 'cursor-default',
          ].join(' ')}
        >
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-inset ring-slate-100">
                <FileText size={13} className="text-slate-500" />
              </span>
              <div className="min-w-0">
                <span className="block text-overline text-slate-500">
                  {t('customers.card_quotes')}
                </span>
                <p className="text-[13px] font-semibold leading-tight text-slate-900 tabular-nums">
                  {quoteCount}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-inset ring-slate-100">
                <TrendingUp size={13} className="text-slate-500" />
              </span>
              <div className="min-w-0">
                <span className="block text-overline text-slate-500">
                  {t('customers.card_total_value')}
                </span>
                <p className="text-[13px] font-semibold leading-tight text-slate-900 tabular-nums">
                  {formatCurrency(c.total_quote_value ?? 0, 'TRY')}
                </p>
              </div>
            </div>
          </div>
          {quoteCount > 0 && (
            <ChevronDown
              size={16}
              className={`shrink-0 text-slate-400 transition-transform duration-200 ${
                expanded ? 'rotate-180' : ''
              }`}
            />
          )}
        </button>

        {/* Expanded quote list */}
        {expanded && (
          <div className="border-t border-slate-100 bg-slate-50/40">
            {quotesLoading ? (
              <div className="px-5 py-3 space-y-2">
                {[0, 1].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded-lg bg-gray-200/70" />
                ))}
              </div>
            ) : quotes.length === 0 ? (
              <p className="px-5 py-3 text-xs text-slate-400">
                {t('customers.card_quotes_not_found')}
              </p>
            ) : (
              <div className="divide-y divide-slate-100/80">
                {quotes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/quotes/${q.id}`)}
                    className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left
                      hover:bg-white/80 transition-colors group"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-semibold text-slate-700 truncate">
                          {q.quote_number}
                        </span>
                      </div>
                      {/* Items summary */}
                      {q.items && q.items.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                          {q.items.slice(0, 3).map((item, idx) => (
                            <span key={idx} className="text-[10px] text-slate-400">
                              {item.honeywell_code || item.description?.slice(0, 15) || '-'}{' '}
                              <span className="text-slate-500">x{item.quantity}</span>
                            </span>
                          ))}
                          {q.items.length > 3 && (
                            <span className="text-[10px] text-slate-400">
                              {t('customers.card_more').replace(
                                '{count}',
                                String(q.items.length - 3),
                              )}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          STATUS_COLORS[q.status] || 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {translateStatus(q.status, t)}
                      </span>
                      <span className="text-xs font-semibold text-slate-700 tabular-nums">
                        {formatCurrency(q.grand_total, q.currency)}
                      </span>
                      <ExternalLink
                        size={12}
                        className="text-slate-300 group-hover:text-honeywell-red transition-colors"
                      />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const INITIAL_FORM = {
  name: '',
  company: '',
  email: '',
  phone: '',
  address: '',
  tax_id: '',
  preferred_lang: 'tr',
  // Auto-enrichment writes website + linkedin_url; reps need the
  // ability to correct bad enrichment manually (audit F-1).
  website: '',
  linkedin_url: '',
  // R6-FORM-3 — Round-5 widened CustomerCreate/CustomerUpdate to also
  // accept these firmographic fields. The form was only updated for
  // website + linkedin_url so reps could see industry/employee_count
  // in the list (CustomerListPage.tsx:130) but not edit them. Territory
  // rollups + parent-account hierarchies were unsettable from the UI.
  industry: '',
  employee_count: '',
  annual_revenue: '',
  parent_id: '',
  territory_id: '',
};

export default function CustomerListPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const importRef = useRef<HTMLInputElement>(null);

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

  const { data, isLoading } = useQuery<PaginatedResponse<Customer>>({
    queryKey: ['customers', { page, search }],
    queryFn: () =>
      customersApi.getCustomers({
        page,
        page_size: 12,
        ...(search && { search }),
      }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof form) => {
      // R6-FORM-3 — backend expects ``industry`` etc. as the right type
      // (number / null), not the form's string state. Coerce here so
      // the input value stays a controlled string but the wire payload
      // matches the Partial<Customer> contract on customersApi.create.
      const toNumberOrNull = (raw: string) => (raw.trim() === '' ? null : Number(raw));
      const wire: Partial<Customer> = {
        name: payload.name,
        company: payload.company,
        email: payload.email,
        phone: payload.phone,
        address: payload.address,
        tax_id: payload.tax_id,
        preferred_lang: payload.preferred_lang,
        website: payload.website || null,
        linkedin_url: payload.linkedin_url || null,
        industry: payload.industry || null,
        employee_count: toNumberOrNull(payload.employee_count),
        annual_revenue: payload.annual_revenue || null,
        parent_id: toNumberOrNull(payload.parent_id),
        territory_id: toNumberOrNull(payload.territory_id),
      };
      return customersApi.createCustomer(wire);
    },
    onSuccess: (newCustomer) => {
      toast.success(t('customers.toast_created'));
      setModalOpen(false);
      setForm(INITIAL_FORM);
      // R7-CACHE-1 — pre-fix only invalidated ['customers']; helper
      // cascades into high-intent + dashboard tiles.
      onCustomerCreated(queryClient);
      // Hydrate the detail-page cache so navigating to the freshly
      // created record doesn't show stale/empty data until F5.
      if (newCustomer?.id != null) {
        queryClient.setQueryData(['customer', newCustomer.id], newCustomer);
      }
    },
    onError: () => toast.error(t('customers.toast_create_failed')),
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => customersApi.importCustomers(file),
    onSuccess: (res) => {
      toast.success(t('customers.toast_imported').replace('{count}', String(res.imported)));
      // R7-CACHE-1 — bulk import emits N customer.created events; same
      // cascade as single create.
      onCustomerCreated(queryClient);
    },
    onError: () => toast.error(t('customers.toast_create_failed')),
  });

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) importMutation.mutate(file);
    e.target.value = '';
  };

  const updateField = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const customers = data?.items || [];
  const totalPages = data?.pages || 1;

  const {
    selectedIds,
    toggleItem,
    toggleAll,
    isSelected,
    clearSelection,
    isAllSelected,
    selectedCount,
  } = useMultiSelect(customers);

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const bulkMutation = useMutation({
    mutationFn: (payload: { ids: number[]; action: string; params?: Record<string, unknown> }) =>
      customersApi.bulkAction(payload),
    onSuccess: (res) => {
      toast.success(res.message);
      clearSelection();
      queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: () => toast.error(t('customers.bulk_failed')),
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
        const ownerIdStr = window.prompt(t('customers.prompt_assign_user_id'));
        if (!ownerIdStr) return;
        const ownerId = parseInt(ownerIdStr, 10);
        if (isNaN(ownerId)) {
          toast.error(t('customers.invalid_user_id'));
          return;
        }
        bulkMutation.mutate({ ids, action: 'assign', params: { created_by: ownerId } });
        return;
      }
    },
    [selectedIds, bulkMutation],
  );

  const BULK_ACTIONS = [
    { key: 'assign', label: t('customers.bulk_assign') },
    { key: 'export', label: t('customers.bulk_export') },
    { key: 'delete', label: t('customers.bulk_delete'), variant: 'danger' as const },
  ];

  return (
    <div>
      <PageHeader title={t('customers.list_title')} description={t('customers.list_description')}>
        <input
          type="file"
          ref={importRef}
          onChange={handleImport}
          accept=".xlsx,.xls,.csv"
          className="hidden"
        />
        <Button
          variant="secondary"
          loading={importMutation.isPending}
          onClick={() => importRef.current?.click()}
        >
          {t('customers.import')}
        </Button>
        <Button onClick={() => setModalOpen(true)}>{t('customers.new')}</Button>
      </PageHeader>

      {/* S-E saved views — universal */}
      <div className="mb-3">
        <SavedViewsBar
          route="/customers"
          queryJson={JSON.stringify({ search, page })}
          onApply={(view) => {
            try {
              const payload = JSON.parse(view.query_json) as {
                search?: string;
                page?: number;
              };
              if (typeof payload.search === 'string') setSearch(payload.search);
              if (typeof payload.page === 'number') setPage(payload.page);
            } catch {
              /* ignore */
            }
          }}
        />
      </div>

      {/* Search + Select All */}
      <div className="mb-6 flex items-center gap-4">
        <div className="max-w-md flex-1">
          <Input
            placeholder={t('customers.search_placeholder')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        {customers.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={toggleAll}
              className="h-4 w-4 rounded border-slate-200 text-blue-600 focus:ring-blue-500"
            />
            {t('customers.select_all')}
          </label>
        )}
      </div>

      {/* Customer Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      ) : customers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-slate-100 mb-5">
            <Users size={36} className="text-slate-400" />
          </div>
          <EmptyState
            title={t('customers.empty_title')}
            description={t('customers.empty_description')}
            action={<Button onClick={() => setModalOpen(true)}>{t('customers.new')}</Button>}
          />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {customers.map((c) => (
              <CustomerCard
                key={c.id}
                customer={c}
                navigate={navigate}
                isSelected={isSelected(c.id)}
                onToggle={toggleItem}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-between">
              <span className="text-sm text-slate-500">
                {t('customers.pagination')
                  .replace('{page}', String(page))
                  .replace('{pages}', String(totalPages))}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  {t('customers.prev')}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  {t('customers.next')}
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* New Customer Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={t('customers.modal_new_title')}
        size="lg"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate(form);
          }}
          className="space-y-5"
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Input
              label={t('customers.name')}
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              required
            />
            <Input
              label={t('customers.company')}
              value={form.company}
              onChange={(e) => updateField('company', e.target.value)}
            />
            <Input
              label={t('customers.email')}
              type="email"
              value={form.email}
              onChange={(e) => updateField('email', e.target.value)}
              required
            />
            <Input
              label={t('customers.phone')}
              value={form.phone}
              onChange={(e) => updateField('phone', e.target.value)}
            />
            <Input
              label={t('customers.tax_id')}
              value={form.tax_id}
              onChange={(e) => updateField('tax_id', e.target.value)}
            />
            <Input
              label={t('customers.preferred_lang')}
              value={form.preferred_lang}
              onChange={(e) => updateField('preferred_lang', e.target.value)}
              placeholder={t('customers.preferred_lang_placeholder')}
            />
          </div>
          <DuplicateWarning
            entityType="customer"
            name={form.name}
            company={form.company}
            email={form.email}
          />
          <Input
            label={t('customers.address')}
            value={form.address}
            onChange={(e) => updateField('address', e.target.value)}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label={t('customers.website')}
              value={form.website}
              onChange={(e) => updateField('website', e.target.value)}
              placeholder="https://"
            />
            <Input
              label={t('customers.linkedin_url')}
              value={form.linkedin_url}
              onChange={(e) => updateField('linkedin_url', e.target.value)}
              placeholder="https://linkedin.com/company/…"
            />
          </div>
          {/* R6-FORM-3 — firmographic fields (industry, employee_count,
              annual_revenue, parent_id, territory_id) accepted by the
              backend since R5-FORM-3/4 but never surfaced in the form. */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Input
              label="Sektör"
              value={form.industry}
              onChange={(e) => updateField('industry', e.target.value)}
              placeholder="Manufacturing"
            />
            <Input
              label="Çalışan sayısı"
              type="number"
              min={0}
              value={form.employee_count}
              onChange={(e) => updateField('employee_count', e.target.value)}
              placeholder="500"
            />
            <Input
              label="Yıllık gelir"
              type="number"
              min={0}
              step="1000"
              value={form.annual_revenue}
              onChange={(e) => updateField('annual_revenue', e.target.value)}
              placeholder="50000000"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Üst hesap (parent customer ID)"
              type="number"
              min={1}
              value={form.parent_id}
              onChange={(e) => updateField('parent_id', e.target.value)}
              placeholder="—"
            />
            <Input
              label="Bölge (territory ID)"
              type="number"
              min={1}
              value={form.territory_id}
              onChange={(e) => updateField('territory_id', e.target.value)}
              placeholder="—"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={createMutation.isPending} className="px-8 shadow-sm">
              {t('common.save')}
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
        title={t('customers.delete_title')}
        message={t('customers.delete_message').replace('{count}', String(selectedCount))}
        confirmLabel={t('common.delete')}
        confirmVariant="danger"
        isLoading={bulkMutation.isPending}
      />
    </div>
  );
}
