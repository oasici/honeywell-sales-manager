import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Trash2, Plus, Pencil, Check, X } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { partsApi, customersApi, pricingApi, pricesApi } from '../../lib/api';
import type { SparePart, Customer, PriceTier, CustomerPricing, PriceEntry } from '../../lib/types';

// ── Tab types ──────────────────────────────────────────

type Tab = 'tiers' | 'customer' | 'margin';

// ── Shared helpers ─────────────────────────────────────

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-medium rounded-lg transition-colors cursor-pointer ${
        active
          ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
          : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
      }`}
    >
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
  const queryClient = useQueryClient();
  const [selectedPartId, setSelectedPartId] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [tierForm, setTierForm] = useState<TierFormState>(EMPTY_TIER_FORM);

  const { data: partsData } = useQuery({
    queryKey: ['parts', 'all'],
    queryFn: () => partsApi.getParts({ limit: 500 }),
  });
  const parts: SparePart[] = partsData?.items ?? [];

  const { data: pricesData } = useQuery({
    queryKey: ['prices', selectedPartId],
    queryFn: () => pricesApi.getPrices({ spare_part_id: selectedPartId, limit: 1 }),
    enabled: selectedPartId !== null,
  });
  const priceEntry: PriceEntry | null = pricesData?.items?.[0] ?? null;

  const { data: tiers = [], isLoading: tiersLoading } = useQuery<PriceTier[]>({
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
      toast.success('Kademe eklendi');
      queryClient.invalidateQueries({ queryKey: ['pricing-tiers', priceEntry?.id] });
      setShowAddForm(false);
      setTierForm(EMPTY_TIER_FORM);
    },
    onError: () => toast.error('Kademe eklenemedi'),
  });

  const deleteTierMutation = useMutation({
    mutationFn: (tierId: number) => pricingApi.deleteTier(tierId),
    onSuccess: () => {
      toast.success('Kademe silindi');
      queryClient.invalidateQueries({ queryKey: ['pricing-tiers', priceEntry?.id] });
    },
    onError: () => toast.error('Kademe silinemedi'),
  });

  const handleAddTier = () => {
    if (!priceEntry) return;
    const minQty = parseInt(tierForm.min_qty, 10);
    const unitPrice = parseFloat(tierForm.unit_price);
    if (isNaN(minQty) || isNaN(unitPrice)) {
      toast.error('Min. adet ve birim fiyat zorunludur');
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
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
          Yedek Parça:
        </label>
        <select
          className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          value={selectedPartId ?? ''}
          onChange={(e) => {
            setSelectedPartId(e.target.value ? Number(e.target.value) : null);
            setShowAddForm(false);
          }}
        >
          <option value="">-- Parça seçiniz --</option>
          {parts.map((p) => (
            <option key={p.id} value={p.id}>
              {p.honeywell_code} — {p.name_tr || p.name_en}
            </option>
          ))}
        </select>
      </div>

      {selectedPartId && !priceEntry && !tiersLoading && (
        <p className="text-sm text-yellow-600 dark:text-yellow-400">
          Bu parça için fiyat girisi bulunamadi. Önce Fiyatlar sayfasinda fiyat ekleyiniz.
        </p>
      )}

      {priceEntry && (
        <>
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Min. Adet
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Max. Adet
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Birim Fiyat
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Indirim %
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500"></th>
                </tr>
              </thead>
              <tbody>
                {tiersLoading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                      Yükleniyor...
                    </td>
                  </tr>
                ) : tiers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                      Kademe bulunamadi
                    </td>
                  </tr>
                ) : (
                  tiers.map((tier) => (
                    <tr
                      key={tier.id}
                      className="border-b border-gray-100 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                    >
                      <td className="px-4 py-3">{tier.min_qty}</td>
                      <td className="px-4 py-3">{tier.max_qty ?? '—'}</td>
                      <td className="px-4 py-3 font-mono">{tier.unit_price.toFixed(2)}</td>
                      <td className="px-4 py-3">%{tier.discount_pct}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => deleteTierMutation.mutate(tier.id)}
                          disabled={deleteTierMutation.isPending}
                          className="rounded p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer"
                          aria-label="Sil"
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
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">Yeni Kademe</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Min. Adet *
                  </label>
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    value={tierForm.min_qty}
                    onChange={(e) => setTierForm((f) => ({ ...f, min_qty: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">Max. Adet</label>
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    value={tierForm.max_qty}
                    onChange={(e) => setTierForm((f) => ({ ...f, max_qty: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Birim Fiyat *
                  </label>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    value={tierForm.unit_price}
                    onChange={(e) => setTierForm((f) => ({ ...f, unit_price: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">Indirim %</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="0.1"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                    value={tierForm.discount_pct}
                    onChange={(e) => setTierForm((f) => ({ ...f, discount_pct: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Button loading={createTierMutation.isPending} onClick={handleAddTier}>
                  Kaydet
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setShowAddForm(false);
                    setTierForm(EMPTY_TIER_FORM);
                  }}
                >
                  İptal
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
              Kademe Ekle
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
  const queryClient = useQueryClient();
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  const [isCreateOpen, setAddModalOpen] = useState(false);
  const [cpForm, setCpForm] = useState<CustomerPricingFormState>(EMPTY_CP_FORM);

  const { data: customersData } = useQuery({
    queryKey: ['customers', 'all'],
    queryFn: () => customersApi.getCustomers({ limit: 500 }),
  });
  const customers: Customer[] = customersData?.items ?? [];

  const { data: partsData } = useQuery({
    queryKey: ['parts', 'all'],
    queryFn: () => partsApi.getParts({ limit: 500 }),
  });
  const parts: SparePart[] = partsData?.items ?? [];

  const { data: customerPricings = [], isLoading: pricingsLoading } = useQuery<CustomerPricing[]>({
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
      toast.success('Müşteri fiyati eklendi');
      queryClient.invalidateQueries({ queryKey: ['customer-pricing', selectedCustomerId] });
      setAddModalOpen(false);
      setCpForm(EMPTY_CP_FORM);
    },
    onError: () => toast.error('Müşteri fiyati eklenemedi'),
  });

  const deleteCpMutation = useMutation({
    mutationFn: (pricingId: number) =>
      pricingApi.deleteCustomerPricing(selectedCustomerId!, pricingId),
    onSuccess: () => {
      toast.success('Müşteri fiyati silindi');
      queryClient.invalidateQueries({ queryKey: ['customer-pricing', selectedCustomerId] });
    },
    onError: () => toast.error('Müşteri fiyati silinemedi'),
  });

  const handleAddSubmit = () => {
    if (!cpForm.spare_part_id || !cpForm.contracted_price) {
      toast.error('Parça ve anlasilan fiyat zorunludur');
      return;
    }
    createCpMutation.mutate(cpForm);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
          Müşteri:
        </label>
        <select
          className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          value={selectedCustomerId ?? ''}
          onChange={(e) => setSelectedCustomerId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">-- Müşteri seçiniz --</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} — {c.company}
            </option>
          ))}
        </select>
      </div>

      {selectedCustomerId && (
        <>
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">Parça</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Anlasilan Fiyat
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">Doviz</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Indirim %
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                    Baslangic
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">Bitis</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500"></th>
                </tr>
              </thead>
              <tbody>
                {pricingsLoading ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                      Yükleniyor...
                    </td>
                  </tr>
                ) : customerPricings.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                      Müşteri fiyati bulunamadi
                    </td>
                  </tr>
                ) : (
                  customerPricings.map((cp) => (
                    <tr
                      key={cp.id}
                      className="border-b border-gray-100 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                    >
                      <td className="px-4 py-3 font-mono text-xs">
                        {cp.spare_part?.part_number ?? `#${cp.spare_part_id}`}
                        {cp.spare_part?.description && (
                          <span className="ml-1 font-sans text-gray-500">
                            {cp.spare_part.description}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono">{cp.contracted_price.toFixed(2)}</td>
                      <td className="px-4 py-3">{cp.currency}</td>
                      <td className="px-4 py-3">%{cp.discount_pct}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">{cp.valid_from ?? '—'}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">{cp.valid_until ?? '—'}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => deleteCpMutation.mutate(cp.id)}
                          disabled={deleteCpMutation.isPending}
                          className="rounded p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer"
                          aria-label="Sil"
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
            Fiyat Ekle
          </Button>
        </>
      )}

      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setAddModalOpen(false);
          setCpForm(EMPTY_CP_FORM);
        }}
        title="Müşteri Özel Fiyat Ekle"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Yedek Parça *</label>
            <select
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
              value={cpForm.spare_part_id}
              onChange={(e) => setCpForm((f) => ({ ...f, spare_part_id: e.target.value }))}
            >
              <option value="">-- Parça seçiniz --</option>
              {parts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.honeywell_code} — {p.name_tr || p.name_en}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Anlasilan Fiyat *
              </label>
              <input
                type="text"
                inputMode="decimal"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                value={cpForm.contracted_price}
                onChange={(e) => {
                  const val = e.target.value.replace(/[^0-9.]/g, '');
                  setCpForm((f) => ({ ...f, contracted_price: val }));
                }}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">Doviz</label>
              <select
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
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
              <label className="mb-1 block text-xs font-medium text-gray-500">Indirim %</label>
              <input
                type="number"
                min={0}
                max={100}
                step="0.1"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                value={cpForm.discount_pct}
                onChange={(e) => setCpForm((f) => ({ ...f, discount_pct: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Baslangic Tarihi
              </label>
              <input
                type="date"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                value={cpForm.valid_from}
                onChange={(e) => setCpForm((f) => ({ ...f, valid_from: e.target.value }))}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">Bitis Tarihi</label>
              <input
                type="date"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                value={cpForm.valid_until}
                onChange={(e) => setCpForm((f) => ({ ...f, valid_until: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Notlar</label>
            <textarea
              rows={2}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 resize-none"
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
              İptal
            </Button>
            <Button loading={createCpMutation.isPending} onClick={handleAddSubmit}>
              Kaydet
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
      toast.success('Marj kuralı guncellendi');
      queryClient.invalidateQueries({ queryKey: ['parts', 'all'] });
      setRowState({ editingId: null, editValue: '' });
    },
    onError: () => toast.error('Marj kuralı guncellenemedi'),
  });

  const handleSaveMargin = (partId: number) => {
    const value = parseFloat(rowState.editValue);
    if (isNaN(value) || value < 0 || value > 100) {
      toast.error('Geçerli bir marj yuzde degeri giriniz (0-100)');
      return;
    }
    updateMarginMutation.mutate({ id: partId, min_margin_pct: value });
  };

  const handleCancelEdit = () => {
    setRowState({ editingId: null, editValue: '' });
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
            <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
              Honeywell Kodu
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">Parça Adi</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">Min. Marj %</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500"></th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                Yükleniyor...
              </td>
            </tr>
          ) : parts.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                Parça bulunamadi
              </td>
            </tr>
          ) : (
            parts.map((part) => {
              const isEditing = rowState.editingId === part.id;
              const marginValue = (part as SparePart & { min_margin_pct?: number }).min_margin_pct;
              return (
                <tr
                  key={part.id}
                  className="border-b border-gray-100 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                >
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-gray-900 dark:text-white">
                    {part.honeywell_code}
                  </td>
                  <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
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
                        className="w-24 rounded border border-blue-400 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-gray-800 dark:text-gray-100"
                        value={rowState.editValue}
                        onChange={(e) => setRowState((s) => ({ ...s, editValue: e.target.value }))}
                        onBlur={() => handleSaveMargin(part.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveMargin(part.id);
                          if (e.key === 'Escape') handleCancelEdit();
                        }}
                      />
                    ) : (
                      <span className="cursor-pointer rounded px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
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
                          aria-label="Kaydet"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                          aria-label="İptal"
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
                        className="rounded p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                        aria-label="Düzenle"
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
  const [activeTab, setActiveTab] = useState<Tab>('tiers');

  return (
    <div>
      <PageHeader title="Fiyatlama Yönetimi" />

      <Card title="">
        {/* Tab Bar */}
        <div className="mb-6 flex gap-1 rounded-xl bg-gray-100 p-1 dark:bg-gray-800/50 w-fit">
          <TabButton
            label="Fiyat Kademeleri"
            active={activeTab === 'tiers'}
            onClick={() => setActiveTab('tiers')}
          />
          <TabButton
            label="Müşteri Özel Fiyatlari"
            active={activeTab === 'customer'}
            onClick={() => setActiveTab('customer')}
          />
          <TabButton
            label="Marj Kuralları"
            active={activeTab === 'margin'}
            onClick={() => setActiveTab('margin')}
          />
        </div>

        {activeTab === 'tiers' && <PriceTiersTab />}
        {activeTab === 'customer' && <CustomerPricingTab />}
        {activeTab === 'margin' && <MarginRulesTab />}
      </Card>
    </div>
  );
}
