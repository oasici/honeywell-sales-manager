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
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { quotesApi, customersApi, partsApi, documentsApi } from '../../lib/api';
import { onQuoteChanged, onQuoteStatusChanged } from '../../lib/cacheInvalidation';
import BundleSelectorModal from './BundleSelectorModal';
import GuidedSellingWizard from './GuidedSellingWizard';
import QuoteComparisonModal from './QuoteComparisonModal';
import { formatCurrency } from '../../lib/formatters';
import { STATUS_COLORS } from '../../lib/constants';
import { translateStatus } from '../../lib/labelTranslations';
import { useT } from '../../hooks/useT';
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
  const t = useT();
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
  // R6-FORM-5 — backend ``QuoteCreate.valid_days`` accepts 1-365.
  // Pre-R6 the form silently dropped the field, so every quote
  // landed on the model default and never expired correctly.
  const [validDays, setValidDays] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<EditableItem[]>([]);
  const [partSearch, setPartSearch] = useState('');
  const [showPartDropdown, setShowPartDropdown] = useState(false);
  const [showCustomerDropdown, setShowCustomerDropdown] = useState(false);
  const [isBundleModalOpen, setIsBundleModalOpen] = useState(false);
  const [isGuidedSellingOpen, setIsGuidedSellingOpen] = useState(false);
  const [isComparisonOpen, setIsComparisonOpen] = useState(false);
  const [customerSelectedIndex, setCustomerSelectedIndex] = useState(-1);
  const [partSelectedIndex, setPartSelectedIndex] = useState(-1);
  const [shareTrackingUrl, setShareTrackingUrl] = useState<string | null>(null);

  // ── Queries ────────────────────────────────────────
  const {
    data: quote,
    isLoading: quoteLoading,
    isError: quoteError,
    refetch: refetchQuote,
  } = useQuery<Quote>({
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
      queueMicrotask(() => {
        setCustomerId(quote.customer_id);
        setLanguage(quote.language);
        setCurrency(quote.currency);
        setTaxRate(quote.tax_rate);
        setValidDays(quote.valid_days ?? null);
        setNotes(quote.notes || '');
        setItems(quote.items.map(itemToEditable));
        if (quote.customer) {
          setCustomerSearch(quote.customer.company || quote.customer.name);
        }
      });
    }
  }, [quote]);

  // ── Mutations ──────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      quoteId ? quotesApi.updateQuote(quoteId, payload) : quotesApi.createQuote(payload),
    onSuccess: (result) => {
      toast.success(quoteId ? t('quotes.editor_toast_updated') : t('quotes.editor_toast_created'));
      onQuoteChanged(queryClient, quoteId ?? result.id);
      if (!quoteId) navigate(`/quotes/${result.id}`, { replace: true });
    },
    onError: () => toast.error(t('quotes.editor_toast_save_failed')),
  });

  const approveMutation = useMutation({
    mutationFn: () => quotesApi.approveQuote(quoteId!),
    onSuccess: () => {
      toast.success(t('quotes.editor_toast_approved'));
      // R4-CACHE-102 — list + notifications + linked opportunity
      // timeline all need to refresh, not just the detail.
      onQuoteStatusChanged(queryClient, quoteId!, quote?.opportunity_id ?? null);
    },
    onError: () => toast.error(t('quotes.editor_toast_approve_failed')),
  });

  const sendMutation = useMutation({
    mutationFn: () => quotesApi.sendQuote(quoteId!),
    onSuccess: () => {
      toast.success(t('quotes.editor_toast_sent'));
      onQuoteStatusChanged(queryClient, quoteId!, quote?.opportunity_id ?? null);
    },
    onError: () => toast.error(t('quotes.editor_toast_send_failed')),
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
      toast.error(t('quotes.editor_select_customer_required'));
      return;
    }
    saveMutation.mutate({
      customer_id: customerId,
      language,
      currency,
      tax_rate: taxRate,
      // R6-FORM-5 — null means "use backend default"; an explicit value
      // overrides the per-tenant default so reps can shorten/lengthen
      // validity for one-off deals.
      valid_days: validDays ?? null,
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
  }, [customerId, language, currency, taxRate, validDays, notes, items, saveMutation, t]);

  const addPartToItems = useCallback((part: SparePart) => {
    const price = part.supplier_price ?? part.transfer_price ?? 0;
    setItems((prev) => [
      ...prev,
      {
        spare_part_id: part.id,
        honeywell_code: part.honeywell_code,
        // Round-4 R4-NAME-1 made name_tr/name_en nullable; coerce to ''
        // so the EditableItem.description string contract holds.
        description: part.name_tr ?? part.name_en ?? '',
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
      setItems((prev) => prev.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
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

  const removeItem = useCallback((index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleGuidedSellingComplete = useCallback(
    (
      guidedItems: {
        spare_part_id: number;
        honeywell_code: string;
        description: string;
        quantity: number;
        unit_price: number;
        discount_pct: number;
      }[],
    ) => {
      setItems((prev) => [
        ...prev,
        ...guidedItems.map((gi, idx) => ({
          spare_part_id: gi.spare_part_id,
          honeywell_code: gi.honeywell_code,
          description: gi.description,
          quantity: gi.quantity,
          unit_price: gi.unit_price,
          discount_pct: gi.discount_pct,
          sort_order: prev.length + idx + 1,
        })),
      ]);
    },
    [],
  );

  const handleAddBundleItems = useCallback(
    (
      bundleItems: {
        spare_part_id: number;
        honeywell_code: string;
        description: string;
        quantity: number;
        unit_price: number;
        discount_pct: number;
      }[],
    ) => {
      setItems((prev) => [
        ...prev,
        ...bundleItems.map((bi, idx) => ({
          spare_part_id: bi.spare_part_id,
          honeywell_code: bi.honeywell_code,
          description: bi.description,
          quantity: bi.quantity,
          unit_price: bi.unit_price,
          discount_pct: bi.discount_pct,
          sort_order: prev.length + idx + 1,
        })),
      ]);
    },
    [],
  );

  const selectCustomer = useCallback((c: Customer) => {
    setCustomerId(c.id);
    setCustomerSearch(c.company || c.name);
    setShowCustomerDropdown(false);
  }, []);

  const handleDownloadPdf = useCallback(async () => {
    if (!quoteId) return;
    try {
      await quotesApi.downloadQuotePdf(quoteId);
    } catch (err: unknown) {
      const apiErr = err as {
        response?: { data?: { error?: { message?: string }; detail?: string } };
      };
      const msg =
        apiErr?.response?.data?.error?.message ||
        apiErr?.response?.data?.detail ||
        t('quotes.editor_pdf_download_failed');
      toast.error(msg);
    }
  }, [quoteId, t]);

  const handleShareLink = useCallback(async () => {
    if (!quoteId || !quote) return;
    const customerEmail = quote.customer?.email || '';
    if (!customerEmail) {
      toast.error(t('quotes.editor_customer_email_missing'));
      return;
    }
    try {
      const result = await documentsApi.share({
        quote_id: quoteId,
        file_name: `${quote.quote_number}.pdf`,
        file_url: `/api/v1/quotes/${quoteId}/pdf`,
        shared_with_email: customerEmail,
      });
      const trackingUrl = `${window.location.origin}${result.data.tracking_url}`;
      setShareTrackingUrl(trackingUrl);
      await navigator.clipboard.writeText(trackingUrl);
      toast.success(t('quotes.editor_share_copied'));
    } catch {
      toast.error(t('quotes.editor_share_failed'));
    }
  }, [quoteId, quote, t]);

  // ── Error state ────────────────────────────────────
  if (!isNew && quoteError) {
    return <QueryErrorBanner variant="block" onRetry={() => refetchQuote()} />;
  }

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
        title={
          isNew
            ? t('quotes.editor_new_title')
            : `${t('quotes.editor_title_prefix')}: ${quote?.quote_number || ''}`
        }
        description={!isNew ? undefined : t('quotes.editor_new_desc')}
      >
        {!isNew && (
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
              STATUS_COLORS[status] || 'bg-slate-100 text-slate-700'
            }`}
          >
            {translateStatus(status, t)}
          </span>
        )}
        {/* R6-RENDER-2 — Quote revision lineage badge. Backend has
            shipped revision_no + superseded_by since R5-API-3 but no
            consumer rendered them. A draft that has been superseded by
            a newer revision should be visibly stale. */}
        {!isNew && quote?.revision_no != null && quote.revision_no > 1 && (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[11px] font-medium ${
              quote?.superseded_by
                ? 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300'
                : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
            }`}
            title={
              quote?.superseded_by
                ? `Bu teklif #${quote.superseded_by} numaralı yeni versiyonla değiştirildi`
                : `Revizyon ${quote.revision_no}`
            }
          >
            Revizyon {quote.revision_no}
            {quote?.superseded_by && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/quotes/${quote.superseded_by}`);
                }}
                className="ml-1 underline underline-offset-2 hover:text-amber-900 dark:hover:text-amber-100"
              >
                · Yeni versiyon →
              </button>
            )}
          </span>
        )}
        <Button variant="secondary" onClick={() => navigate('/quotes')}>
          {t('common.back')}
        </Button>
        {(!quoteId || status === 'draft' || status === 'pending_approval') && (
          <Button loading={saveMutation.isPending} onClick={handleSave}>
            {t('common.save')}
          </Button>
        )}
        {quoteId && status === 'draft' && (
          <Button
            variant="secondary"
            loading={approveMutation.isPending}
            onClick={() => approveMutation.mutate()}
            className="bg-green-600! text-white! hover:bg-green-700!"
          >
            {t('quotes.editor_approve_label')}
          </Button>
        )}
        {quoteId && status === 'approved' && (
          <Button
            variant="secondary"
            loading={sendMutation.isPending}
            onClick={() => sendMutation.mutate()}
            className="bg-blue-600! text-white! hover:bg-blue-700!"
          >
            {t('quotes.editor_send_label')}
          </Button>
        )}
        {quoteId && (
          <Button variant="secondary" onClick={handleDownloadPdf}>
            {t('common.download_pdf')}
          </Button>
        )}
        {quoteId && (
          <Button variant="secondary" onClick={handleShareLink}>
            {t('common.share_link')}
          </Button>
        )}
        {shareTrackingUrl && (
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(shareTrackingUrl);
              toast.success(t('quotes.editor_link_copied'));
            }}
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-mono text-slate-600 hover:bg-slate-100 transition-colors truncate max-w-xs"
            title={shareTrackingUrl}
          >
            {shareTrackingUrl}
          </button>
        )}
        {quoteId && quote && quote.version > 1 && (
          <Button variant="secondary" onClick={() => setIsComparisonOpen(true)}>
            {t('quotes.editor_versions_compare')}
          </Button>
        )}
      </PageHeader>

      <div className="space-y-6">
        {/* ── Customer Section ──────────────────────── */}
        <Card title={t('quotes.editor_customer_card')}>
          <div className="relative max-w-md">
            <Input
              label={t('quotes.editor_customer_search_label')}
              placeholder={t('quotes.editor_customer_search_ph')}
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
                  // Round-10 R10-FE-13 — the >=0 guard + dropdown bound
                  // ensures the index resolves to a Customer.
                  const picked = items[customerSelectedIndex];
                  if (picked) {
                    selectCustomer(picked);
                  }
                  setCustomerSelectedIndex(-1);
                } else if (e.key === 'Escape') {
                  setShowCustomerDropdown(false);
                  setCustomerSelectedIndex(-1);
                }
              }}
            />
            {showCustomerDropdown && customerResults?.items && customerResults.items.length > 0 && (
              <div className="absolute z-20 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg max-h-48 overflow-y-auto">
                {customerResults.items.map((c, idx) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => selectCustomer(c)}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-slate-50 transition-colors ${
                      idx === customerSelectedIndex ? 'bg-honeywell-red/10' : ''
                    }`}
                  >
                    <span className="font-medium">{c.company || c.name}</span>
                    {c.company && c.name && <span className="text-slate-500"> - {c.name}</span>}
                    <span className="ml-2 text-xs text-slate-400">{c.email}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Card>

        {/* ── Settings Row ──────────────────────────── */}
        <Card title={t('quotes.editor_settings_card')}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Select
              label={t('quotes.editor_language')}
              options={[
                { value: 'tr', label: 'Türkçe' },
                { value: 'en', label: 'English' },
              ]}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            />
            <Select
              label={t('quotes.editor_currency')}
              options={CURRENCY_OPTIONS}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            />
            <Input
              label={t('quotes.editor_tax_rate')}
              type="number"
              min={0}
              max={100}
              value={taxRate}
              onChange={(e) => setTaxRate(Number(e.target.value))}
            />
            <Input
              label="Geçerlilik (gün)"
              type="number"
              min={1}
              max={365}
              placeholder="30"
              value={validDays ?? ''}
              onChange={(e) => {
                const raw = e.target.value;
                setValidDays(raw === '' ? null : Number(raw));
              }}
            />
          </div>
        </Card>

        {/* ── Items Table ───────────────────────────── */}
        <Card
          title={t('quotes.editor_items_card')}
          action={
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => setIsGuidedSellingOpen(true)}>
                {t('quotes.editor_guided_selling')}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setIsBundleModalOpen(true)}>
                {t('quotes.editor_add_bundle')}
              </Button>
              <div className="relative">
                <Input
                  placeholder={t('quotes.editor_part_search_ph')}
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
                      const picked = parts[partSelectedIndex];
                      if (picked) {
                        addPartToItems(picked);
                      }
                      setPartSelectedIndex(-1);
                    } else if (e.key === 'Escape') {
                      setShowPartDropdown(false);
                      setPartSelectedIndex(-1);
                    }
                  }}
                  className="w-56!"
                />
                {showPartDropdown && partResults?.items && partResults.items.length > 0 && (
                  <div className="absolute right-0 z-20 mt-1 w-80 rounded-lg border border-slate-200 bg-white shadow-lg max-h-48 overflow-y-auto">
                    {partResults.items.map((p, idx) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => addPartToItems(p)}
                        className={`w-full px-4 py-2 text-left text-sm hover:bg-slate-50 transition-colors ${
                          idx === partSelectedIndex ? 'bg-honeywell-red/10' : ''
                        }`}
                      >
                        <span className="font-mono font-semibold text-xs">{p.honeywell_code}</span>
                        <span className="ml-2 text-slate-600">{p.name_tr || p.name_en}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          }
        >
          {items.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">
              {t('quotes.editor_items_empty')}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="px-2 py-2 text-xs font-semibold text-slate-500 w-24">
                      {t('quotes.editor_col_row')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-slate-500">
                      {t('quotes.editor_col_code')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-slate-500">
                      {t('quotes.editor_col_desc')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-slate-500 w-20">
                      {t('quotes.editor_col_qty')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-slate-500 w-28">
                      {t('quotes.editor_col_unit_price')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-slate-500 w-20">
                      {t('quotes.editor_col_discount')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-slate-500 w-28 text-right">
                      {t('quotes.editor_col_total')}
                    </th>
                    <th className="px-3 py-2 w-10" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => {
                    const lineGross = item.quantity * item.unit_price;
                    const lineNet = lineGross - lineGross * (item.discount_pct / 100);
                    return (
                      <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-2 py-2">
                          <div className="flex items-center gap-1">
                            <span className="text-slate-500 w-5 text-center">{idx + 1}</span>
                            <button
                              type="button"
                              onClick={() => addBlankItemAfter(idx)}
                              className="flex h-5 w-5 items-center justify-center rounded bg-green-50 text-green-600 hover:bg-green-100 transition-colors text-xs font-bold"
                              title={t('quotes.editor_add_line_tooltip')}
                            >
                              +
                            </button>
                            <button
                              type="button"
                              onClick={() => removeItem(idx)}
                              disabled={items.length <= 1}
                              className={`flex h-5 w-5 items-center justify-center rounded text-xs font-bold transition-colors ${
                                items.length <= 1
                                  ? 'bg-slate-50 text-slate-300 cursor-not-allowed'
                                  : 'bg-red-50 text-red-500 hover:bg-red-100'
                              }`}
                              title={t('quotes.editor_remove_line_tooltip')}
                            >
                              -
                            </button>
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.honeywell_code}
                            onChange={(e) => updateItem(idx, 'honeywell_code', e.target.value)}
                            className="w-full rounded border border-slate-200 px-2 py-1 text-xs font-mono focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.description}
                            onChange={(e) => updateItem(idx, 'description', e.target.value)}
                            className="w-full rounded border border-slate-200 px-2 py-1 text-sm focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min={1}
                            value={item.quantity}
                            onChange={(e) => updateItem(idx, 'quantity', Number(e.target.value))}
                            className="w-full rounded border border-slate-200 px-2 py-1 text-sm text-right focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min={0}
                            step={0.01}
                            value={item.unit_price}
                            onChange={(e) => updateItem(idx, 'unit_price', Number(e.target.value))}
                            className="w-full rounded border border-slate-200 px-2 py-1 text-sm text-right focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
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
                              updateItem(idx, 'discount_pct', Number(e.target.value))
                            }
                            className="w-full rounded border border-slate-200 px-2 py-1 text-sm text-right focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-light"
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
                                ? 'text-slate-200 cursor-not-allowed'
                                : 'text-slate-400 hover:bg-red-50 hover:text-red-600'
                            }`}
                            title={t('quotes.editor_remove_line_tooltip')}
                          >
                            <svg
                              className="h-4 w-4"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                              />
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
        <Card title={t('quotes.editor_summary_card')}>
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Receipt-style item list */}
            <div className="flex-1 min-w-0">
              {items.length > 0 ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 font-mono text-xs">
                  {items.map((item, idx) => {
                    const lineGross = item.quantity * item.unit_price;
                    const lineNet = lineGross - lineGross * (item.discount_pct / 100);
                    return (
                      <div
                        key={idx}
                        className="py-2 border-b border-dashed border-slate-200 last:border-b-0"
                      >
                        <div className="mb-1">
                          <span className="text-slate-900 font-semibold">
                            {item.honeywell_code}
                          </span>
                          <span className="text-slate-400 mx-1.5">-</span>
                          <span className="text-slate-600">{item.description}</span>
                        </div>
                        <div className="text-right tabular-nums">
                          <span className="text-slate-500">
                            {item.quantity} x {formatCurrency(item.unit_price, currency)}
                          </span>
                          <span className="ml-3 font-semibold text-slate-900">
                            {formatCurrency(lineNet, currency)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-slate-400 italic">{t('quotes.editor_summary_empty')}</p>
              )}
            </div>

            {/* Totals */}
            <div className="w-full max-w-xs shrink-0 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">{t('quotes.editor_subtotal')}:</span>
                <span className="font-medium">{formatCurrency(subtotal, currency)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">{t('quotes.editor_discount')}:</span>
                <span className="font-medium text-red-600">
                  -{formatCurrency(discountTotal, currency)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">
                  {t('quotes.editor_tax')} (%{taxRate}):
                </span>
                <span className="font-medium">{formatCurrency(taxAmount, currency)}</span>
              </div>
              <hr className="border-slate-200" />
              <div className="flex justify-between text-base">
                <span className="font-semibold text-slate-900">
                  {t('quotes.editor_grand_total')}:
                </span>
                <span className="font-bold text-honeywell-red">
                  {formatCurrency(grandTotal, currency)}
                </span>
              </div>
            </div>
          </div>
        </Card>

        {/* ── Notes ─────────────────────────────────── */}
        <Card title={t('quotes.editor_notes')}>
          <textarea
            className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm
              placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-honeywell-light
              focus:border-honeywell-red"
            rows={4}
            placeholder={t('quotes.editor_notes_placeholder')}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Card>
      </div>

      <BundleSelectorModal
        isOpen={isBundleModalOpen}
        onClose={() => setIsBundleModalOpen(false)}
        onAddItems={handleAddBundleItems}
      />

      <GuidedSellingWizard
        isOpen={isGuidedSellingOpen}
        onClose={() => setIsGuidedSellingOpen(false)}
        onComplete={handleGuidedSellingComplete}
      />

      {quoteId && (
        <QuoteComparisonModal
          isOpen={isComparisonOpen}
          onClose={() => setIsComparisonOpen(false)}
          quoteId={quoteId}
        />
      )}
    </div>
  );
}
