import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { quotesApi, customersApi, partsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { STATUS_LABELS, STATUS_COLORS } from '../../lib/constants';
import type { Quote, QuoteItem, Customer, SparePart } from '../../lib/types';

interface EditableItem {
  id?: number;
  spare_part_id: number | null;
  honeywell_code: string;
  description: string;
  quantity: number;
  unit_price: number;
  discount_pct: number;
  sort_order: number;
}

const LANGUAGE_OPTIONS = [
  { value: 'tr', label: 'Turkce' },
  { value: 'en', label: 'Ingilizce' },
];

const CURRENCY_OPTIONS = [
  { value: 'TRY', label: 'TRY' },
  { value: 'USD', label: 'USD' },
  { value: 'EUR', label: 'EUR' },
];

function itemToEditable(item: QuoteItem, idx: number): EditableItem {
  return {
    id: item.id,
    spare_part_id: item.spare_part_id,
    honeywell_code: item.honeywell_code,
    description: item.description,
    quantity: item.quantity,
    unit_price: item.unit_price,
    discount_pct: item.discount_pct,
    sort_order: item.sort_order || idx + 1,
  };
}

export default function QuoteEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isNew = id === 'new' || !id;
  const quoteId = isNew ? null : Number(id);

  // ── State ──────────────────────────────────────────
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [customerSearch, setCustomerSearch] = useState('');
  const [language, setLanguage] = useState('tr');
  const [currency, setCurrency] = useState('USD');
  const [taxRate, setTaxRate] = useState(20);
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<EditableItem[]>([]);
  const [partSearch, setPartSearch] = useState('');
  const [showPartDropdown, setShowPartDropdown] = useState(false);
  const [showCustomerDropdown, setShowCustomerDropdown] = useState(false);
  const [customerSelectedIndex, setCustomerSelectedIndex] = useState(-1);
  const [partSelectedIndex, setPartSelectedIndex] = useState(-1);

  // ── Queries ────────────────────────────────────────
  const { data: quote, isLoading: quoteLoading } = useQuery<Quote>({
    queryKey: ['quote', quoteId],
    queryFn: () => quotesApi.getQuote(quoteId!),
    enabled: !!quoteId,
  });

  const { data: customerResults } = useQuery<{ items: Customer[] }>({
    queryKey: ['customers-search', customerSearch],
    queryFn: () => customersApi.getCustomers({ search: customerSearch, page_size: 10 }),
    enabled: customerSearch.length >= 2,
  });

  const { data: partResults } = useQuery<{ items: SparePart[] }>({
    queryKey: ['parts-search', partSearch],
    queryFn: () => partsApi.getParts({ search: partSearch, page_size: 10 }),
    enabled: partSearch.length >= 2,
  });

  // ── Populate from existing quote ───────────────────
  useEffect(() => {
    if (quote) {
      setCustomerId(quote.customer_id);
      setLanguage(quote.language);
      setCurrency(quote.currency);
      setTaxRate(quote.tax_rate);
      setNotes(quote.notes || '');
      setItems(quote.items.map(itemToEditable));
      if (quote.customer) {
        setCustomerSearch(quote.customer.company || quote.customer.name);
      }
    }
  }, [quote]);

  // ── Mutations ──────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      quoteId
        ? quotesApi.updateQuote(quoteId, payload)
        : quotesApi.createQuote(payload),
    onSuccess: (result) => {
      toast.success(quoteId ? 'Teklif guncellendi' : 'Teklif olusturuldu');
      queryClient.invalidateQueries({ queryKey: ['quotes'] });
      if (!quoteId) navigate(`/quotes/${result.id}`, { replace: true });
      else queryClient.invalidateQueries({ queryKey: ['quote', quoteId] });
    },
    onError: () => toast.error('Kaydetme basarisiz'),
  });

  const approveMutation = useMutation({
    mutationFn: () => quotesApi.approveQuote(quoteId!),
    onSuccess: () => {
      toast.success('Teklif onaylandi');
      queryClient.invalidateQueries({ queryKey: ['quote', quoteId] });
    },
    onError: () => toast.error('Onaylama basarisiz'),
  });

  const sendMutation = useMutation({
    mutationFn: () => quotesApi.sendQuote(quoteId!),
    onSuccess: () => {
      toast.success('Teklif gonderildi');
      queryClient.invalidateQueries({ queryKey: ['quote', quoteId] });
    },
    onError: () => toast.error('Gonderme basarisiz'),
  });

  // ── Calculations ───────────────────────────────────
  const { subtotal, discountTotal, taxAmount, grandTotal } = useMemo(() => {
    let sub = 0;
    let disc = 0;
    items.forEach((item) => {
      const lineGross = item.quantity * item.unit_price;
      const lineDisc = lineGross * (item.discount_pct / 100);
      sub += lineGross;
      disc += lineDisc;
    });
    const net = sub - disc;
    const tax = net * (taxRate / 100);
    return {
      subtotal: sub,
      discountTotal: disc,
      taxAmount: tax,
      grandTotal: net + tax,
    };
  }, [items, taxRate]);

  // ── Handlers ───────────────────────────────────────
  const handleSave = useCallback(() => {
    if (!customerId) {
      toast.error('Lutfen musteri secin');
      return;
    }
    saveMutation.mutate({
      customer_id: customerId,
      language,
      currency,
      tax_rate: taxRate,
      notes,
      items: items.map((item, idx) => ({
        spare_part_id: item.spare_part_id,
        honeywell_code: item.honeywell_code,
        description: item.description,
        quantity: item.quantity,
        unit_price: item.unit_price,
        discount_pct: item.discount_pct,
        sort_order: idx + 1,
      })),
    });
  }, [customerId, language, currency, taxRate, notes, items, saveMutation]);

  const addPartToItems = useCallback((part: SparePart) => {
    const price = part.supplier_price ?? part.transfer_price ?? 0;
    setItems((prev) => [
      ...prev,
      {
        spare_part_id: part.id,
        honeywell_code: part.honeywell_code,
        description: part.name_tr || part.name_en,
        quantity: 1,
        unit_price: price,
        discount_pct: 0,
        sort_order: prev.length + 1,
      },
    ]);
    setPartSearch('');
    setShowPartDropdown(false);
  }, []);

  const updateItem = useCallback(
    (index: number, field: keyof EditableItem, value: string | number) => {
      setItems((prev) =>
        prev.map((item, i) => (i === index ? { ...item, [field]: value } : item)),
      );
    },
    [],
  );

  const addBlankItemAfter = useCallback((index: number) => {
    setItems((prev) => {
      const blank: EditableItem = {
        spare_part_id: null,
        honeywell_code: '',
        description: '',
        quantity: 1,
        unit_price: 0,
        discount_pct: 0,
        sort_order: prev.length + 1,
      };
      const next = [...prev];
      next.splice(index + 1, 0, blank);
      return next;
    });
  }, []);

  const removeLastItem = useCallback(() => {
    setItems((prev) => (prev.length <= 1 ? prev : prev.slice(0, -1)));
  }, []);

  const removeItem = useCallback((index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const selectCustomer = useCallback((c: Customer) => {
    setCustomerId(c.id);
    setCustomerSearch(c.company || c.name);
    setShowCustomerDropdown(false);
  }, []);

  const handleDownloadPdf = useCallback(async () => {
    if (!quoteId) return;
    try {
      await quotesApi.downloadQuotePdf(quoteId);
    } catch (err: any) {
      const msg = err?.response?.data?.error?.message
        || err?.response?.data?.detail
        || 'PDF indirilemedi';
      toast.error(msg);
    }
  }, [quoteId]);

  // ── Loading state ──────────────────────────────────
  if (!isNew && quoteLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  const status = quote?.status || 'draft';

  return (
    <div>
      {/* ── Header ──────────────────────────────────── */}
      <PageHeader
        title={isNew ? 'Yeni Teklif' : `Teklif: ${quote?.quote_number || ''}`}
        description={
          !isNew
            ? undefined
            : 'Yeni teklif olusturun'
        }
      >
        {!isNew && (
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
              STATUS_COLORS[status] || 'bg-gray-100 text-gray-700'
            }`}
          >
            {STATUS_LABELS[status] || status}
          </span>
        )}
        <Button variant="secondary" onClick={() => navigate('/quotes')}>
          Geri Don
        </Button>
        {(!quoteId || status === 'draft' || status === 'pending_approval') && (
          <Button
            loading={saveMutation.isPending}
            onClick={handleSave}
          >
            Kaydet
          </Button>
        )}
        {quoteId && status === 'draft' && (
          <Button
            variant="secondary"
            loading={approveMutation.isPending}
            onClick={() => approveMutation.mutate()}
            className="!bg-green-600 !text-white hover:!bg-green-700"
          >
            Onayla
          </Button>
        )}
        {quoteId && status === 'approved' && (
          <Button
            variant="secondary"
            loading={sendMutation.isPending}
            onClick={() => sendMutation.mutate()}
            className="!bg-blue-600 !text-white hover:!bg-blue-700"
          >
            Gonder
          </Button>
        )}
        {quoteId && (
          <Button variant="secondary" onClick={handleDownloadPdf}>
            PDF Indir
          </Button>
        )}
      </PageHeader>

      <div className="space-y-6">
        {/* ── Customer Section ──────────────────────── */}
        <Card title="Musteri">
          <div className="relative max-w-md">
            <Input
              label="Musteri Ara"
              placeholder="Sirket veya isim yazin..."
              value={customerSearch}
              onChange={(e) => {
                setCustomerSearch(e.target.value);
                setShowCustomerDropdown(true);
                setCustomerSelectedIndex(-1);
              }}
              onFocus={() => setShowCustomerDropdown(true)}
              onKeyDown={(e) => {
                const items = customerResults?.items || [];
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setCustomerSelectedIndex((prev) => Math.min(prev + 1, items.length - 1));
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setCustomerSelectedIndex((prev) => Math.max(prev - 1, 0));
                } else if (e.key === 'Enter' && customerSelectedIndex >= 0) {
                  e.preventDefault();
                  selectCustomer(items[customerSelectedIndex]);
                  setCustomerSelectedIndex(-1);
                } else if (e.key === 'Escape') {
                  setShowCustomerDropdown(false);
                  setCustomerSelectedIndex(-1);
                }
              }}
            />
            {showCustomerDropdown && customerResults?.items && customerResults.items.length > 0 && (
              <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto">
                {customerResults.items.map((c, idx) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => selectCustomer(c)}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors ${
                      idx === customerSelectedIndex ? 'bg-honeywell-red/10' : ''
                    }`}
                  >
                    <span className="font-medium">{c.company || c.name}</span>
                    {c.company && c.name && (
                      <span className="text-gray-500"> - {c.name}</span>
                    )}
                    <span className="ml-2 text-xs text-gray-400">{c.email}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Card>

        {/* ── Settings Row ──────────────────────────── */}
        <Card title="Teklif Ayarlari">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Select
              label="Dil"
              options={LANGUAGE_OPTIONS}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            />
            <Select
              label="Para Birimi"
              options={CURRENCY_OPTIONS}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            />
            <Input
              label="KDV Orani (%)"
              type="number"
              min={0}
              max={100}
              value={taxRate}
              onChange={(e) => setTaxRate(Number(e.target.value))}
            />
          </div>
        </Card>

        {/* ── Items Table ───────────────────────────── */}
        <Card
          title="Kalemler"
          action={
            <div className="relative">
              <Input
                placeholder="Parca kodu ile ara..."
                value={partSearch}
                onChange={(e) => {
                  setPartSearch(e.target.value);
                  setShowPartDropdown(true);
                  setPartSelectedIndex(-1);
                }}
                onFocus={() => setShowPartDropdown(true)}
                onKeyDown={(e) => {
                  const parts = partResults?.items || [];
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setPartSelectedIndex((prev) => Math.min(prev + 1, parts.length - 1));
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setPartSelectedIndex((prev) => Math.max(prev - 1, 0));
                  } else if (e.key === 'Enter' && partSelectedIndex >= 0) {
                    e.preventDefault();
                    addPartToItems(parts[partSelectedIndex]);
                    setPartSelectedIndex(-1);
                  } else if (e.key === 'Escape') {
                    setShowPartDropdown(false);
                    setPartSelectedIndex(-1);
                  }
                }}
                className="!w-56"
              />
              {showPartDropdown && partResults?.items && partResults.items.length > 0 && (
                <div className="absolute right-0 z-20 mt-1 w-80 rounded-lg border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto">
                  {partResults.items.map((p, idx) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => addPartToItems(p)}
                      className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors ${
                        idx === partSelectedIndex ? 'bg-honeywell-red/10' : ''
                      }`}
                    >
                      <span className="font-mono font-semibold text-xs">
                        {p.honeywell_code}
                      </span>
                      <span className="ml-2 text-gray-600">
                        {p.name_tr || p.name_en}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          }
        >
          {items.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-500">
              Henuz kalem eklenmedi. Yukardaki arama kutusundan parca ekleyin.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-2 py-2 text-xs font-semibold text-gray-500 w-24">
                      Sira
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                      Honeywell Kodu
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                      Aciklama
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 w-20">
                      Adet
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 w-28">
                      Birim Fiyat
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 w-20">
                      Iskonto %
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 w-28 text-right">
                      Toplam
                    </th>
                    <th className="px-3 py-2 w-10" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => {
                    const lineGross = item.quantity * item.unit_price;
                    const lineNet =
                      lineGross - lineGross * (item.discount_pct / 100);
                    return (
                      <tr
                        key={idx}
                        className="border-b border-gray-100 hover:bg-gray-50"
                      >
                        <td className="px-2 py-2">
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500 w-5 text-center">{idx + 1}</span>
                            <button
                              type="button"
                              onClick={() => addBlankItemAfter(idx)}
                              className="flex h-5 w-5 items-center justify-center rounded bg-green-50 text-green-600 hover:bg-green-100 transition-colors text-xs font-bold"
                              title="Alt satira yeni kalem ekle"
                            >
                              +
                            </button>
                            <button
                              type="button"
                              onClick={() => removeItem(idx)}
                              disabled={items.length <= 1}
                              className={`flex h-5 w-5 items-center justify-center rounded text-xs font-bold transition-colors ${
                                items.length <= 1
                                  ? 'bg-gray-50 text-gray-300 cursor-not-allowed'
                                  : 'bg-red-50 text-red-500 hover:bg-red-100'
                              }`}
                              title="Bu kalemi sil"
                            >
                              -
                            </button>
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.honeywell_code}
                            onChange={(e) =>
                              updateItem(idx, 'honeywell_code', e.target.value)
                            }
                            className="w-full rounded border border-gray-200 px-2 py-1 text-xs font-mono focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.description}
                            onChange={(e) =>
                              updateItem(idx, 'description', e.target.value)
                            }
                            className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min={1}
                            value={item.quantity}
                            onChange={(e) =>
                              updateItem(idx, 'quantity', Number(e.target.value))
                            }
                            className="w-full rounded border border-gray-200 px-2 py-1 text-sm text-right focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min={0}
                            step={0.01}
                            value={item.unit_price}
                            onChange={(e) =>
                              updateItem(
                                idx,
                                'unit_price',
                                Number(e.target.value),
                              )
                            }
                            className="w-full rounded border border-gray-200 px-2 py-1 text-sm text-right focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            value={item.discount_pct}
                            onChange={(e) =>
                              updateItem(
                                idx,
                                'discount_pct',
                                Number(e.target.value),
                              )
                            }
                            className="w-full rounded border border-gray-200 px-2 py-1 text-sm text-right focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2 text-right font-medium">
                          {formatCurrency(lineNet, currency)}
                        </td>
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => removeItem(idx)}
                            disabled={items.length <= 1}
                            className={`rounded p-1 transition-colors ${
                              items.length <= 1
                                ? 'text-gray-200 cursor-not-allowed'
                                : 'text-gray-400 hover:bg-red-50 hover:text-red-600'
                            }`}
                            title="Kalemi sil"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* ── Summary ───────────────────────────────── */}
        <Card title="Ozet">
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Receipt-style item list */}
            <div className="flex-1 min-w-0">
              {items.length > 0 ? (
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 font-mono text-xs">
                  {items.map((item, idx) => {
                    const lineGross = item.quantity * item.unit_price;
                    const lineNet = lineGross - lineGross * (item.discount_pct / 100);
                    return (
                      <div key={idx} className="py-2 border-b border-dashed border-gray-300 last:border-b-0">
                        <div className="mb-1">
                          <span className="text-gray-900 font-semibold">{item.honeywell_code}</span>
                          <span className="text-gray-400 mx-1.5">-</span>
                          <span className="text-gray-600">{item.description}</span>
                        </div>
                        <div className="text-right tabular-nums">
                          <span className="text-gray-500">{item.quantity} x {formatCurrency(item.unit_price, currency)}</span>
                          <span className="ml-3 font-semibold text-gray-900">{formatCurrency(lineNet, currency)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-400 italic">Henuz kalem eklenmedi</p>
              )}
            </div>

            {/* Totals */}
            <div className="w-full max-w-xs shrink-0 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Alt Toplam:</span>
                <span className="font-medium">
                  {formatCurrency(subtotal, currency)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Iskonto:</span>
                <span className="font-medium text-red-600">
                  -{formatCurrency(discountTotal, currency)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">KDV (%{taxRate}):</span>
                <span className="font-medium">
                  {formatCurrency(taxAmount, currency)}
                </span>
              </div>
              <hr className="border-gray-200" />
              <div className="flex justify-between text-base">
                <span className="font-semibold text-gray-900">Genel Toplam:</span>
                <span className="font-bold text-honeywell-red">
                  {formatCurrency(grandTotal, currency)}
                </span>
              </div>
            </div>
          </div>
        </Card>

        {/* ── Notes ─────────────────────────────────── */}
        <Card title="Notlar">
          <textarea
            className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
              placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-light
              focus:border-honeywell-red"
            rows={4}
            placeholder="Teklif notu ekleyin..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Card>
      </div>
    </div>
  );
}
