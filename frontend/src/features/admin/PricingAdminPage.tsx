import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Trash2, Plus, Pencil, Check, X } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { partsApi, customersApi, pricingApi, pricesApi } from '../../lib/api';
import { onPricingChanged } from '../../lib/cacheInvalidation';
import type { SparePart, Customer, PriceTier, CustomerPricing, PriceEntry } from '../../lib/types';
import { useT } from '../../hooks/useT';

// ── Tab types ──────────────────────────────────────────

type Tab = 'tiers' | 'customer' | 'margin';

// ── Shared helpers ─────────────────────────────────────

/**
 * TabButton — segmented tab item that mirrors the design-system pattern
 * (slate-50 well + white active pill). Used by the Pricing admin tab strip.
 */
function TabButton({
  label,
  active,
  onClick,
  icon,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={[
        'inline-flex h-9 items-center gap-2 rounded-[10px] px-3 text-[13px] font-medium transition-all',
        'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
        active
          ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
          : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
      ].join(' ')}
    >
      {icon}
      {label}
    </button>
  );
}

// ── Tab 1: Price Tiers ────────────────────────────────

interface TierFormState {
  min_qty: string;
  max_qty: string;
  unit_price: string;
  discount_pct: string;
}

const EMPTY_TIER_FORM: TierFormState = {
  min_qty: '',
  max_qty: '',
  unit_price: '',
  discount_pct: '0',
};

function PriceTiersTab() {
  const t = useT();
  const queryClient = useQueryClient();
  const [selectedPartId, setSelectedPartId] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [tierForm, setTierForm] = useState<TierFormState>(EMPTY_TIER_FORM);

  // R14-FE-1 exempt: parts list is a dropdown option source; if it
  // fails the user sees an empty <select> which is acceptable — the
  // priceEntry/tier queries below own the visible failure surface.
  const { data: partsData } = useQuery({
    queryKey: ['parts', 'all'],
    queryFn: () => partsApi.getParts({ limit: 500 }),
  });
  const parts: SparePart[] = partsData?.items ?? [];

  // R14-FE-1 exempt: pricesData hydrates the priceEntry pointer used
  // by the tiers query; tiers query already surfaces an error banner.
  const { data: pricesData } = useQuery({
    queryKey: ['prices', selectedPartId],
    queryFn: () => pricesApi.getPrices({ spare_part_id: selectedPartId, limit: 1 }),
    enabled: selectedPartId !== null,
  });
  const priceEntry: PriceEntry | null = pricesData?.items?.[0] ?? null;

  const {
    data: tiers = [],
    isLoading: tiersLoading,
    isError: tiersIsError,
    refetch: refetchTiers,
  } = useQuery<PriceTier[]>({
    queryKey: ['pricing-tiers', priceEntry?.id],
    queryFn: async () => {
      const res = await pricingApi.getTiers(priceEntry!.id);
      if (Array.isArray(res)) return res as PriceTier[];
      const typed = res as { tiers?: PriceTier[]; items?: PriceTier[] };
      return typed.tiers ?? typed.items ?? [];
    },
    enabled: priceEntry !== null,
  });

  const createTierMutation = useMutation({
    mutationFn: (payload: {
      price_entry_id: number;
      min_qty: number;
      max_qty?: number;
      unit_price: number;
      discount_pct?: number;
    }) => pricingApi.createTier(payload),
    onSuccess: () => {
      toast.success(t('pricing_admin.toast_tier_added'));
      onPricingChanged(queryClient, priceEntry?.id);
      setShowAddForm(false);
      setTierForm(EMPTY_TIER_FORM);
    },
    onError: () => toast.error(t('pricing_admin.toast_tier_add_fail')),
  });

  const deleteTierMutation = useMutation({
    mutationFn: (tierId: number) => pricingApi.deleteTier(tierId),
    onSuccess: () => {
      toast.success(t('pricing_admin.toast_tier_deleted'));
      onPricingChanged(queryClient, priceEntry?.id);
    },
    onError: () => toast.error(t('pricing_admin.toast_tier_delete_fail')),
  });

  const handleAddTier = () => {
    if (!priceEntry) return;
    const minQty = parseInt(tierForm.min_qty, 10);
    const unitPrice = parseFloat(tierForm.unit_price);
    if (isNaN(minQty) || isNaN(unitPrice)) {
      toast.error(t('pricing_admin.err_min_unit'));
      return;
    }
    const maxQty = tierForm.max_qty ? parseInt(tierForm.max_qty, 10) : undefined;
    const discountPct = parseFloat(tierForm.discount_pct) || 0;
    createTierMutation.mutate({
      price_entry_id: priceEntry.id,
      min_qty: minQty,
      ...(maxQty !== undefined && { max_qty: maxQty }),
      unit_price: unitPrice,
      discount_pct: discountPct,
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 whitespace-nowrap">
          {t('pricing_admin.spare_part_label')}
        </label>
        <select
          className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
          value={selectedPartId ?? ''}
          onChange={(e) => {
            setSelectedPartId(e.target.value ? Number(e.target.value) : null);
            setShowAddForm(false);
          }}
        >
          <option value="">{t('pricing_admin.select_part')}</option>
          {parts.map((p) => (
            <option key={p.id} value={p.id}>
              {p.honeywell_code} — {p.name_tr || p.name_en}
            </option>
          ))}
        </select>
      </div>

      {selectedPartId && !priceEntry && !tiersLoading && (
        <p className="text-sm text-yellow-600 dark:text-yellow-400">
          {t('pricing_admin.no_price_entry')}
        </p>
      )}

      {priceEntry && tiersIsError && (
        <QueryErrorBanner variant="inline" onRetry={() => refetchTiers()} />
      )}

      {priceEntry && !tiersIsError && (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.col_min_qty')}
                  </th>
                  {/* R6-RESP-1 — collapse max-qty + discount-pct on mobile. */}
                  <th className="hidden px-4 py-3 text-xs font-semibold uppercase text-slate-500 sm:table-cell">
                    {t('pricing_admin.col_max_qty')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.col_unit_price')}
                  </th>
                  <th className="hidden px-4 py-3 text-xs font-semibold uppercase text-slate-500 sm:table-cell">
                    {t('pricing_admin.col_discount_pct')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500"></th>
                </tr>
              </thead>
              <tbody>
                {tiersLoading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                      {t('subscription.loading')}
                    </td>
                  </tr>
                ) : tiers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                      {t('pricing_admin.tiers_empty')}
                    </td>
                  </tr>
                ) : (
                  tiers.map((tier) => (
                    <tr
                      key={tier.id}
                      className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                    >
                      <td className="px-4 py-3">{tier.min_qty}</td>
                      <td className="hidden px-4 py-3 sm:table-cell">{tier.max_qty ?? '—'}</td>
                      <td className="px-4 py-3 font-mono">{tier.unit_price.toFixed(2)}</td>
                      <td className="hidden px-4 py-3 sm:table-cell">%{tier.discount_pct}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => deleteTierMutation.mutate(tier.id)}
                          disabled={deleteTierMutation.isPending}
                          className="rounded p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer"
                          aria-label={t('common.delete')}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {showAddForm ? (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-700 dark:bg-blue-900/10 space-y-3">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                {t('pricing_admin.new_tier')}
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">
                    {t('pricing_admin.lbl_min_qty_req')}
                  </label>
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                    value={tierForm.min_qty}
                    onChange={(e) => setTierForm((f) => ({ ...f, min_qty: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">
                    {t('pricing_admin.lbl_max_qty')}
                  </label>
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                    value={tierForm.max_qty}
                    onChange={(e) => setTierForm((f) => ({ ...f, max_qty: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">
                    {t('pricing_admin.lbl_unit_price_req')}
                  </label>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                    value={tierForm.unit_price}
                    onChange={(e) => setTierForm((f) => ({ ...f, unit_price: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">
                    {t('pricing_admin.lbl_discount_pct')}
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="0.1"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                    value={tierForm.discount_pct}
                    onChange={(e) => setTierForm((f) => ({ ...f, discount_pct: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Button loading={createTierMutation.isPending} onClick={handleAddTier}>
                  {t('common.save')}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setShowAddForm(false);
                    setTierForm(EMPTY_TIER_FORM);
                  }}
                >
                  {t('common.cancel')}
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="secondary"
              onClick={() => setShowAddForm(true)}
              className="inline-flex items-center gap-1.5"
            >
              <Plus size={15} />
              {t('pricing_admin.add_tier')}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

// ── Tab 2: Customer Contracted Prices ─────────────────

interface CustomerPricingFormState {
  spare_part_id: string;
  contracted_price: string;
  currency: string;
  discount_pct: string;
  valid_from: string;
  valid_until: string;
  notes: string;
}

const EMPTY_CP_FORM: CustomerPricingFormState = {
  spare_part_id: '',
  contracted_price: '',
  currency: 'USD',
  discount_pct: '0',
  valid_from: '',
  valid_until: '',
  notes: '',
};

function CustomerPricingTab() {
  const t = useT();
  const queryClient = useQueryClient();
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  const [isCreateOpen, setAddModalOpen] = useState(false);
  const [cpForm, setCpForm] = useState<CustomerPricingFormState>(EMPTY_CP_FORM);

  // R14-FE-1 exempt: customers list is a dropdown option source; if it
  // fails the user sees an empty <select> which is acceptable — the
  // customer-pricing query owns the visible failure surface.
  const { data: customersData } = useQuery({
    queryKey: ['customers', 'all'],
    queryFn: () => customersApi.getCustomers({ limit: 500 }),
  });
  const customers: Customer[] = customersData?.items ?? [];

  // R14-FE-1 exempt: parts list is dropdown option source (see above).
  const { data: partsData } = useQuery({
    queryKey: ['parts', 'all'],
    queryFn: () => partsApi.getParts({ limit: 500 }),
  });
  const parts: SparePart[] = partsData?.items ?? [];

  const {
    data: customerPricings = [],
    isLoading: pricingsLoading,
    isError: pricingsIsError,
    refetch: refetchPricings,
  } = useQuery<CustomerPricing[]>({
    queryKey: ['customer-pricing', selectedCustomerId],
    queryFn: async () => {
      const res = await pricingApi.getCustomerPricing(selectedCustomerId!);
      if (Array.isArray(res)) return res as CustomerPricing[];
      const typed = res as { pricings?: CustomerPricing[]; items?: CustomerPricing[] };
      return typed.pricings ?? typed.items ?? [];
    },
    enabled: selectedCustomerId !== null,
  });

  const createCpMutation = useMutation({
    mutationFn: (payload: CustomerPricingFormState) =>
      pricingApi.createCustomerPricing(selectedCustomerId!, {
        spare_part_id: Number(payload.spare_part_id),
        contracted_price: parseFloat(payload.contracted_price),
        currency: payload.currency || 'USD',
        discount_pct: parseFloat(payload.discount_pct) || 0,
        ...(payload.valid_from && { valid_from: payload.valid_from }),
        ...(payload.valid_until && { valid_until: payload.valid_until }),
        ...(payload.notes && { notes: payload.notes }),
      }),
    onSuccess: () => {
      toast.success(t('pricing_admin.toast_cp_added'));
      onPricingChanged(queryClient, null, selectedCustomerId);
      setAddModalOpen(false);
      setCpForm(EMPTY_CP_FORM);
    },
    onError: () => toast.error(t('pricing_admin.toast_cp_add_fail')),
  });

  const deleteCpMutation = useMutation({
    mutationFn: (pricingId: number) =>
      pricingApi.deleteCustomerPricing(selectedCustomerId!, pricingId),
    onSuccess: () => {
      toast.success(t('pricing_admin.toast_cp_deleted'));
      onPricingChanged(queryClient, null, selectedCustomerId);
    },
    onError: () => toast.error(t('pricing_admin.toast_cp_delete_fail')),
  });

  const handleAddSubmit = () => {
    if (!cpForm.spare_part_id || !cpForm.contracted_price) {
      toast.error(t('pricing_admin.err_part_price'));
      return;
    }
    createCpMutation.mutate(cpForm);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 whitespace-nowrap">
          {t('pricing_admin.customer_label')}
        </label>
        <select
          className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
          value={selectedCustomerId ?? ''}
          onChange={(e) => setSelectedCustomerId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t('pricing_admin.select_customer')}</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} — {c.company}
            </option>
          ))}
        </select>
      </div>

      {selectedCustomerId && pricingsIsError && (
        <QueryErrorBanner variant="inline" onRetry={() => refetchPricings()} />
      )}

      {selectedCustomerId && !pricingsIsError && (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.col_part')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.th_agreed_price')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.lbl_currency_short')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.col_discount_pct')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.lbl_valid_from')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                    {t('pricing_admin.lbl_valid_until')}
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500"></th>
                </tr>
              </thead>
              <tbody>
                {pricingsLoading ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                      {t('subscription.loading')}
                    </td>
                  </tr>
                ) : customerPricings.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                      {t('pricing_admin.customer_price_empty')}
                    </td>
                  </tr>
                ) : (
                  customerPricings.map((cp) => (
                    <tr
                      key={cp.id}
                      className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                    >
                      <td className="px-4 py-3 font-mono text-xs">
                        {cp.spare_part?.part_number ?? `#${cp.spare_part_id}`}
                        {cp.spare_part?.description && (
                          <span className="ml-1 font-sans text-slate-500">
                            {cp.spare_part.description}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono">{cp.contracted_price.toFixed(2)}</td>
                      <td className="px-4 py-3">{cp.currency}</td>
                      <td className="px-4 py-3">%{cp.discount_pct}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">{cp.valid_from ?? '—'}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">{cp.valid_until ?? '—'}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => deleteCpMutation.mutate(cp.id)}
                          disabled={deleteCpMutation.isPending}
                          className="rounded p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer"
                          aria-label={t('common.delete')}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <Button
            variant="secondary"
            onClick={() => setAddModalOpen(true)}
            className="inline-flex items-center gap-1.5"
          >
            <Plus size={15} />
            {t('pricing_admin.btn_add_price')}
          </Button>
        </>
      )}

      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setAddModalOpen(false);
          setCpForm(EMPTY_CP_FORM);
        }}
        title={t('pricing_admin.modal_add_customer_price')}
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              {t('pricing_admin.lbl_spare_part_req')}
            </label>
            <select
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
              value={cpForm.spare_part_id}
              onChange={(e) => setCpForm((f) => ({ ...f, spare_part_id: e.target.value }))}
            >
              <option value="">{t('pricing_admin.select_part')}</option>
              {parts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.honeywell_code} — {p.name_tr || p.name_en}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {t('pricing_admin.col_agreed_price')}
              </label>
              <input
                type="text"
                inputMode="decimal"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                value={cpForm.contracted_price}
                onChange={(e) => {
                  const val = e.target.value.replace(/[^0-9.]/g, '');
                  setCpForm((f) => ({ ...f, contracted_price: val }));
                }}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {t('pricing_admin.lbl_currency_short')}
              </label>
              <select
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                value={cpForm.currency}
                onChange={(e) => setCpForm((f) => ({ ...f, currency: e.target.value }))}
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="TRY">TRY</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {t('pricing_admin.lbl_discount_pct')}
              </label>
              <input
                type="number"
                min={0}
                max={100}
                step="0.1"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                value={cpForm.discount_pct}
                onChange={(e) => setCpForm((f) => ({ ...f, discount_pct: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {t('pricing_admin.lbl_valid_from')}
              </label>
              <input
                type="date"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                value={cpForm.valid_from}
                onChange={(e) => setCpForm((f) => ({ ...f, valid_from: e.target.value }))}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {t('pricing_admin.lbl_valid_until')}
              </label>
              <input
                type="date"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100"
                value={cpForm.valid_until}
                onChange={(e) => setCpForm((f) => ({ ...f, valid_until: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              {t('pricing_admin.lbl_notes')}
            </label>
            <textarea
              rows={2}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100 resize-none"
              value={cpForm.notes}
              onChange={(e) => setCpForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <Button
              variant="secondary"
              onClick={() => {
                setAddModalOpen(false);
                setCpForm(EMPTY_CP_FORM);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button loading={createCpMutation.isPending} onClick={handleAddSubmit}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ── Tab 3: Margin Rules ───────────────────────────────

interface MarginRowState {
  editingId: number | null;
  editValue: string;
}

function MarginRulesTab() {
  const t = useT();
  const queryClient = useQueryClient();
  const [rowState, setRowState] = useState<MarginRowState>({ editingId: null, editValue: '' });

  const { data: partsData, isLoading } = useQuery({
    queryKey: ['parts', 'all'],
    queryFn: () => partsApi.getParts({ limit: 500 }),
  });
  const parts: SparePart[] = partsData?.items ?? [];

  const updateMarginMutation = useMutation({
    mutationFn: ({ id, min_margin_pct }: { id: number; min_margin_pct: number }) =>
      pricingApi.updateMargin(id, min_margin_pct),
    onSuccess: () => {
      toast.success(t('pricing_admin.toast_margin_ok'));
      onPricingChanged(queryClient);
      setRowState({ editingId: null, editValue: '' });
    },
    onError: () => toast.error(t('pricing_admin.toast_margin_fail')),
  });

  const handleSaveMargin = (partId: number) => {
    const value = parseFloat(rowState.editValue);
    if (isNaN(value) || value < 0 || value > 100) {
      toast.error(t('pricing_admin.err_margin_pct'));
      return;
    }
    updateMarginMutation.mutate({ id: partId, min_margin_pct: value });
  };

  const handleCancelEdit = () => {
    setRowState({ editingId: null, editValue: '' });
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
            <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
              {t('pricing_admin.col_hw_code')}
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
              {t('pricing_admin.col_part_name')}
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
              {t('pricing_admin.col_min_margin')}
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500"></th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-slate-400">
                {t('subscription.loading')}
              </td>
            </tr>
          ) : parts.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-slate-400">
                {t('pricing_admin.parts_empty')}
              </td>
            </tr>
          ) : (
            parts.map((part) => {
              const isEditing = rowState.editingId === part.id;
              const marginValue = (part as SparePart & { min_margin_pct?: number }).min_margin_pct;
              return (
                <tr
                  key={part.id}
                  className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-900 dark:text-white">
                    {part.honeywell_code}
                  </td>
                  <td className="px-4 py-3 text-slate-700 dark:text-slate-300">
                    {part.name_tr || part.name_en}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        autoFocus
                        className="w-24 rounded border border-blue-400 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-slate-800 dark:text-slate-100"
                        value={rowState.editValue}
                        onChange={(e) => setRowState((s) => ({ ...s, editValue: e.target.value }))}
                        onBlur={() => handleSaveMargin(part.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveMargin(part.id);
                          if (e.key === 'Escape') handleCancelEdit();
                        }}
                      />
                    ) : (
                      <span className="cursor-pointer rounded px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                        {marginValue != null ? `%${marginValue}` : '—'}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleSaveMargin(part.id)}
                          className="rounded p-1 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors cursor-pointer"
                          aria-label={t('pricing_admin.aria_save')}
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                          aria-label={t('pricing_admin.aria_cancel')}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() =>
                          setRowState({
                            editingId: part.id,
                            editValue: marginValue != null ? String(marginValue) : '',
                          })
                        }
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                        aria-label={t('pricing_admin.aria_edit')}
                      >
                        <Pencil size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────

export default function PricingAdminPage() {
  const t = useT();
  const [activeTab, setActiveTab] = useState<Tab>('tiers');

  return (
    <div>
      <PageHeader
        title={t('pricing_admin.title')}
        description="Fiyat kademeleri, müşteri özel fiyatları ve marj kurallarını tek panelden yönetin"
      />

      {/* Tab strip — segmented control on a slate-tinted well, matches the
          rest of the app. Sits above the active panel so the entire panel
          can keep its own card shell. */}
      <div
        className="mb-4 inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
        role="tablist"
        aria-label="Fiyatlama sekmeleri"
      >
        <TabButton
          label={t('pricing_admin.tab_tiers')}
          active={activeTab === 'tiers'}
          onClick={() => setActiveTab('tiers')}
        />
        <TabButton
          label={t('pricing_admin.tab_customer')}
          active={activeTab === 'customer'}
          onClick={() => setActiveTab('customer')}
        />
        <TabButton
          label={t('pricing_admin.tab_margin')}
          active={activeTab === 'margin'}
          onClick={() => setActiveTab('margin')}
        />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        {activeTab === 'tiers' && <PriceTiersTab />}
        {activeTab === 'customer' && <CustomerPricingTab />}
        {activeTab === 'margin' && <MarginRulesTab />}
      </div>
    </div>
  );
}
