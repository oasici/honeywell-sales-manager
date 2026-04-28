import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { customersApi, quotesApi, customerHealthApi, aiApi, opportunitiesApi } from '../../lib/api';
import { formatCurrency, formatDate, formatDateTime } from '../../lib/formatters';
import {
  translateActivityType,
  translateOpportunityStage,
  translateSeverity,
  translateSignalType,
  translateStatus,
} from '../../lib/labelTranslations';

// Map quote status → Badge variant. Mirrors QuoteListPage so the visual
// language stays identical across surfaces.
type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'default';
const QUOTE_STATUS_TONE: Record<string, BadgeTone> = {
  draft: 'default',
  pending_approval: 'warning',
  approved: 'success',
  sent: 'info',
  accepted: 'success',
  rejected: 'danger',
  expired: 'warning',
  cancelled: 'default',
};
import { useT } from '../../hooks/useT';
import {
  Mail,
  Phone,
  MapPin,
  FileText,
  TrendingUp,
  Sparkles,
  ShieldAlert,
  Globe,
  ExternalLink,
  Users,
  Building2,
  CalendarClock,
  RefreshCw,
  Pin,
  PinOff,
} from 'lucide-react';
import { Badge } from '../../components/ui/Badge';
import { HealthScoreCard } from './HealthScoreCard';
import AccountTeamPanel from './AccountTeamPanel';
import CommentThread from '../board/CommentThread';
import { SummarySourceLinks } from '../../components/ai/SummarySourceLinks';
import type {
  Customer,
  Quote,
  PaginatedResponse,
  CustomerHealthReport,
  AiSummarizeResponse,
  Opportunity,
  ChurnPredictionResult,
  CustomerIntelligenceResponse,
  Account360Response,
} from '../../lib/types';

export default function CustomerDetailPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const customerId = Number(id);

  const [editing, setEditing] = useState(false);
  const [meetingPrepText, setMeetingPrepText] = useState<string | null>(null);
  const [aggregateRefreshing, setAggregateRefreshing] = useState(false);
  const [changesOpen, setChangesOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    company: '',
    email: '',
    phone: '',
    address: '',
    tax_id: '',
    preferred_lang: '',
  });

  const { data: customer, isLoading } = useQuery<Customer>({
    queryKey: ['customer', customerId],
    queryFn: () => customersApi.getCustomer(customerId),
    enabled: !!customerId,
  });

  const { data: quotesData, isLoading: quotesLoading } = useQuery<PaginatedResponse<Quote>>({
    queryKey: ['customer-quotes', customerId],
    queryFn: () => quotesApi.getQuotes({ customer_id: customerId, page_size: 50 }),
    enabled: !!customerId,
  });

  const { data: healthData, isLoading: healthLoading } = useQuery<CustomerHealthReport>({
    queryKey: ['customer-health', customerId],
    queryFn: () => customerHealthApi.getCustomerHealth(customerId),
    enabled: !!customerId,
  });

  const { data: timelineData } = useQuery<{
    events: {
      type: string;
      id: number;
      title: string;
      detail: string;
      status: string;
      timestamp: string;
    }[];
  }>({
    queryKey: ['customer-timeline', customerId],
    queryFn: () => customersApi.getTimeline(customerId),
    enabled: !!customerId,
  });

  const { data: activityData } = useQuery<{
    activities: {
      id: number;
      activity_type: string;
      entity_type: string;
      entity_id: number;
      summary: string;
      created_at: string;
    }[];
  }>({
    queryKey: ['customer-activity-timeline', customerId],
    queryFn: () => customersApi.getActivityTimeline(customerId),
    enabled: !!customerId,
  });

  const { data: hierarchy } = useQuery<{
    customer_id: number;
    parents: { id: number; name: string; company: string }[];
    subsidiaries: { id: number; name: string; company: string }[];
  }>({
    queryKey: ['customer-hierarchy', customerId],
    queryFn: () => customersApi.getHierarchy(customerId),
    enabled: !!customerId,
  });

  const { data: rollup } = useQuery<{
    subsidiary_count: number;
    total_opportunities: number;
    total_opportunity_value: number;
    total_quotes: number;
    total_quote_value: number;
  }>({
    queryKey: ['customer-rollup', customerId],
    queryFn: () => customersApi.getRollup(customerId),
    enabled: !!customerId && (hierarchy?.subsidiaries?.length ?? 0) > 0,
  });

  // AI Summary
  const { data: aiSummary, isLoading: aiSummaryLoading } = useQuery<AiSummarizeResponse>({
    queryKey: ['ai-customer-summary', customerId],
    queryFn: () => aiApi.summarize({ entity_type: 'customer', entity_id: customerId }),
    enabled: !!customerId,
    retry: false,
  });

  const { data: aiChanges, isLoading: aiChangesLoading } = useQuery<AiSummarizeResponse>({
    queryKey: ['ai-customer-changes', customerId, 7],
    queryFn: () =>
      aiApi.summarizeChanges({ entity_type: 'customer', entity_id: customerId, days: 7 }),
    enabled: !!customerId && changesOpen,
    retry: false,
  });

  const refreshChangesMutation = useMutation({
    mutationFn: () =>
      aiApi.summarizeChanges({
        entity_type: 'customer',
        entity_id: customerId,
        days: 7,
        force: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-customer-changes', customerId, 7] });
      toast.success(t('settings.operation_success'));
      setChangesOpen(true);
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  // Churn prediction
  const { data: churnPrediction, isLoading: churnLoading } = useQuery<{
    data: ChurnPredictionResult;
  }>({
    queryKey: ['ai-predict-churn', customerId],
    queryFn: () => aiApi.predictChurn(customerId),
    enabled: !!customerId,
    retry: false,
  });

  // Inline opportunities
  const { data: oppsData } = useQuery<{ items: Opportunity[] }>({
    queryKey: ['customer-opportunities', customerId],
    queryFn: () => opportunitiesApi.list({ customer_id: customerId }),
    enabled: !!customerId,
  });

  const { data: intelligence } = useQuery<CustomerIntelligenceResponse>({
    queryKey: ['customer-intelligence', customerId],
    queryFn: () => customersApi.getIntelligence(customerId),
    enabled: !!customerId,
    staleTime: 60_000,
  });

  const { data: account360, isLoading: account360Loading } = useQuery<Account360Response>({
    queryKey: ['account-360', customerId],
    queryFn: () => customersApi.getAccount360(customerId),
    enabled: !!customerId,
    staleTime: 60_000,
  });

  const meetingPrepMutation = useMutation({
    mutationFn: () => aiApi.meetingPrep(customerId),
    onSuccess: (d) => {
      setMeetingPrepText(d.prep);
      toast.success(t('account360.meeting_prep_done'));
    },
    onError: () => toast.error(t('account360.meeting_prep_failed')),
  });

  useEffect(() => {
    if (customer) {
      queueMicrotask(() =>
        setForm({
          name: customer.name || '',
          company: customer.company || '',
          email: customer.email || '',
          phone: customer.phone || '',
          address: customer.address || '',
          tax_id: customer.tax_id || '',
          preferred_lang: customer.preferred_lang || '',
        }),
      );
    }
  }, [customer]);

  const updateMutation = useMutation({
    mutationFn: (payload: typeof form) => customersApi.updateCustomer(customerId, payload),
    onSuccess: () => {
      toast.success(t('customer_detail.toast_updated'));
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ['customer', customerId] });
    },
    onError: () => toast.error(t('customer_detail.toast_update_failed')),
  });

  const enrichMutation = useMutation({
    mutationFn: () => customersApi.enrich(customerId),
    onSuccess: () => {
      toast.success(t('customer_detail.toast_enriched'));
      queryClient.invalidateQueries({ queryKey: ['customer', customerId] });
    },
    onError: () => toast.error(t('customer_detail.toast_enrich_failed')),
  });

  const pinMutation = useMutation({
    mutationFn: async (pin: boolean) => {
      if (pin) await customersApi.pinCustomer(customerId);
      else await customersApi.unpinCustomer(customerId);
    },
    onSuccess: (_, pin) => {
      queryClient.invalidateQueries({ queryKey: ['customer', customerId] });
      queryClient.invalidateQueries({ queryKey: ['high-intent-accounts'] });
      toast.success(pin ? t('high_intent.pinned') : t('high_intent.unpinned'));
    },
    onError: () => toast.error(t('high_intent.pin_error')),
  });

  const updateField = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  if (isLoading) {
    return (
      <div>
        <PageHeader title="…" />
        <div className="space-y-4">
          <Skeleton variant="card" count={2} />
        </div>
      </div>
    );
  }

  if (!customer) {
    return (
      <div>
        <PageHeader title={t('customer_detail.not_found')} />
        <div className="rounded-2xl border border-slate-200 bg-white py-16 text-center shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <p className="text-[14px] text-slate-500 dark:text-slate-400">
            {t('customer_detail.not_found')}
          </p>
          <div className="mt-5">
            <Button variant="secondary" onClick={() => navigate('/customers')}>
              {t('customer_detail.back')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const quotes = quotesData?.items || [];
  const totalValue = quotes.reduce((sum, q) => sum + q.grand_total, 0);

  const quoteColumns = [
    {
      key: 'quote_number',
      header: t('customer_detail.quote_no'),
      render: (row: Quote) => (
        <button
          type="button"
          onClick={() => navigate(`/quotes/${row.id}`)}
          className="text-[13px] font-semibold tabular-nums text-slate-900 transition-colors hover:text-honeywell-red dark:text-white"
        >
          {row.quote_number}
        </button>
      ),
    },
    {
      key: 'status',
      header: t('customer_detail.status'),
      render: (row: Quote) => {
        const tone = QUOTE_STATUS_TONE[row.status] ?? 'default';
        return (
          <Badge variant={tone} size="sm" dot>
            {translateStatus(row.status, t)}
          </Badge>
        );
      },
    },
    {
      key: 'grand_total',
      header: t('customer_detail.total'),
      align: 'right' as const,
      numeric: true,
      render: (row: Quote) => (
        <span className="text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
          {formatCurrency(row.grand_total, row.currency)}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: t('customer_detail.date'),
      render: (row: Quote) => (
        <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {formatDate(row.created_at)}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={customer.company || customer.name}
        description={customer.company ? customer.name : undefined}
      >
        <Button variant="secondary" onClick={() => navigate('/customers')}>
          {t('customer_detail.back')}
        </Button>
        <Button
          variant="secondary"
          loading={pinMutation.isPending}
          disabled={editing}
          onClick={() => pinMutation.mutate(!customer.pinned)}
          title={customer.pinned ? t('high_intent.unpin') : t('high_intent.pin')}
        >
          {customer.pinned ? (
            <>
              <PinOff size={14} className="mr-1" />
              {t('high_intent.unpin')}
            </>
          ) : (
            <>
              <Pin size={14} className="mr-1" />
              {t('high_intent.pin')}
            </>
          )}
        </Button>
        {editing ? (
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setEditing(false);
                // Reset form
                if (customer) {
                  setForm({
                    name: customer.name || '',
                    company: customer.company || '',
                    email: customer.email || '',
                    phone: customer.phone || '',
                    address: customer.address || '',
                    tax_id: customer.tax_id || '',
                    preferred_lang: customer.preferred_lang || '',
                  });
                }
              }}
            >
              {t('customer_detail.cancel')}
            </Button>
            <Button loading={updateMutation.isPending} onClick={() => updateMutation.mutate(form)}>
              {t('customer_detail.save')}
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="secondary"
              loading={enrichMutation.isPending}
              onClick={() => enrichMutation.mutate()}
            >
              <Sparkles size={14} className="mr-1" />
              {t('customer_detail.enrich')}
            </Button>
            <Button onClick={() => setEditing(true)}>{t('customer_detail.edit')}</Button>
          </>
        )}
      </PageHeader>

      <div className="space-y-6">
        {/* Customer Info */}
        <Card title={t('customer_detail.info_title')}>
          {editing ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
              <div className="sm:col-span-2">
                <Input
                  label={t('customers.address')}
                  value={form.address}
                  onChange={(e) => updateField('address', e.target.value)}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Customer hero — avatar + name stack so the page anchor is
                  unambiguous even when a long company name wraps. */}
              <div className="flex items-start gap-3.5">
                <span
                  aria-hidden
                  className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-honeywell-red/10 text-[16px] font-bold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20"
                >
                  {(customer.company || customer.name)?.trim()?.[0]?.toUpperCase() ?? '?'}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="text-heading-3 text-slate-900 dark:text-white">
                    {customer.company || customer.name}
                  </h3>
                  {customer.company && (
                    <p className="mt-0.5 text-[13px] text-slate-500 dark:text-slate-400">
                      {customer.name}
                    </p>
                  )}
                  {customer.pinned && (
                    <div className="mt-2">
                      <Badge variant="warning" size="sm">
                        <Pin size={10} />
                        {t('customer_detail.pinned_badge')}
                      </Badge>
                    </div>
                  )}
                </div>
              </div>

              {/* Contact info — icon medallions for visual rhythm. Empty
                  values render an em-dash so columns line up cleanly. */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                    <Mail size={14} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-overline text-slate-400 dark:text-slate-500">
                      {t('customer_detail.lbl_email')}
                    </p>
                    <p className="truncate text-[13px] text-slate-800 dark:text-slate-200">
                      {customer.email || '—'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                    <Phone size={14} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-overline text-slate-400 dark:text-slate-500">
                      {t('customer_detail.lbl_phone')}
                    </p>
                    <p className="truncate text-[13px] text-slate-800 dark:text-slate-200">
                      {customer.phone || '—'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                    <FileText size={14} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-overline text-slate-400 dark:text-slate-500">
                      {t('customer_detail.lbl_tax_id')}
                    </p>
                    <p className="truncate text-[13px] tabular-nums text-slate-800 dark:text-slate-200">
                      {customer.tax_id || '—'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-[11px] font-bold text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                    {customer.preferred_lang === 'tr'
                      ? 'TR'
                      : customer.preferred_lang === 'en'
                        ? 'EN'
                        : '—'}
                  </span>
                  <div className="min-w-0">
                    <p className="text-overline text-slate-400 dark:text-slate-500">
                      {t('customer_detail.lbl_preferred_lang')}
                    </p>
                    <p className="truncate text-[13px] text-slate-800 dark:text-slate-200">
                      {customer.preferred_lang === 'tr'
                        ? t('customer_detail.lang_tr')
                        : customer.preferred_lang === 'en'
                          ? t('customer_detail.lang_en')
                          : t('customer_detail.lang_unspecified')}
                    </p>
                  </div>
                </div>
                {customer.address && (
                  <div className="flex items-start gap-3 sm:col-span-2">
                    <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                      <MapPin size={14} />
                    </span>
                    <div className="min-w-0">
                      <p className="text-overline text-slate-400 dark:text-slate-500">
                        {t('customer_detail.lbl_address')}
                      </p>
                      <p className="text-[13px] leading-5 text-slate-800 dark:text-slate-200">
                        {customer.address}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* AI Enrichment data — brand-tinted divider so it visually
                  separates "facts we entered" from "facts AI inferred". */}
              {customer.enriched_at && (
                <div className="mt-2 rounded-2xl border border-honeywell-red/15 bg-honeywell-red/4 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                      <Sparkles size={14} />
                    </span>
                    <Badge variant="default" size="sm">
                      {t('customer_detail.ai_enriched')}
                    </Badge>
                    <span className="text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                      {formatDate(customer.enriched_at)}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    {customer.industry && (
                      <div className="flex items-center gap-2.5">
                        <Building2 size={14} className="shrink-0 text-slate-400" />
                        <Badge variant="default" size="sm">
                          {customer.industry}
                        </Badge>
                      </div>
                    )}
                    {customer.employee_count != null && (
                      <div className="flex items-center gap-2.5">
                        <Users size={14} className="shrink-0 text-slate-400" />
                        <span className="text-[13px] tabular-nums text-slate-700 dark:text-slate-200">
                          {customer.employee_count.toLocaleString()}{' '}
                          {t('customer_detail.employees_suffix')}
                        </span>
                      </div>
                    )}
                    {customer.annual_revenue && (
                      <div className="flex items-center gap-2.5">
                        <TrendingUp size={14} className="shrink-0 text-slate-400" />
                        <span className="text-[13px] tabular-nums text-slate-700 dark:text-slate-200">
                          {customer.annual_revenue}
                        </span>
                      </div>
                    )}
                    {customer.website && (
                      <div className="flex items-center gap-2.5">
                        <Globe size={14} className="shrink-0 text-slate-400" />
                        <a
                          href={customer.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="truncate text-[13px] font-medium text-honeywell-red hover:underline"
                        >
                          {customer.website}
                        </a>
                      </div>
                    )}
                    {customer.linkedin_url && (
                      <div className="flex items-center gap-2.5">
                        <ExternalLink size={14} className="shrink-0 text-slate-400" />
                        <a
                          href={customer.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[13px] font-medium text-honeywell-red hover:underline"
                        >
                          {t('customer_detail.linkedin')}
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* Health Score — hero position */}
        {healthLoading ? (
          <Skeleton variant="card" />
        ) : healthData ? (
          <HealthScoreCard health={healthData} />
        ) : null}

        {/* Account 360 — Sprint 3 */}
        {account360Loading ? (
          <Skeleton variant="card" />
        ) : account360 ? (
          <Card title={t('account360.title')}>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Button
                variant="secondary"
                size="sm"
                loading={aggregateRefreshing}
                onClick={async () => {
                  setAggregateRefreshing(true);
                  try {
                    await queryClient.fetchQuery({
                      queryKey: ['account-360', customerId],
                      queryFn: () => customersApi.getAccount360(customerId, { refresh: true }),
                    });
                    toast.success(t('account360.refreshed'));
                  } finally {
                    setAggregateRefreshing(false);
                  }
                }}
              >
                <RefreshCw size={14} className="mr-1" />
                {t('account360.refresh_metrics')}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                loading={meetingPrepMutation.isPending}
                onClick={() => meetingPrepMutation.mutate()}
              >
                <CalendarClock size={14} className="mr-1" />
                {t('account360.meeting_prep')}
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                <p className="text-xs text-slate-500">{t('account360.pipeline_open')}</p>
                <p className="text-lg font-bold text-slate-900 dark:text-white">
                  {formatCurrency(
                    account360.enrichment.pipeline_open_amount,
                    account360.enrichment.currency || 'TRY',
                  )}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                <p className="text-xs text-slate-500">{t('account360.closed_won')}</p>
                <p className="text-lg font-bold text-slate-900 dark:text-white">
                  {formatCurrency(
                    account360.enrichment.closed_won_revenue,
                    account360.enrichment.currency || 'TRY',
                  )}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                <p className="text-xs text-slate-500">{t('account360.risk_index')}</p>
                <p className="text-lg font-bold text-slate-900 dark:text-white">
                  {account360.enrichment.risk_index}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                <p className="text-xs text-slate-500">{t('account360.engagement')}</p>
                <p className="text-lg font-bold text-slate-900 dark:text-white">
                  {account360.enrichment.engagement_score}
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 text-sm">
              <div>
                <span className="text-slate-500">{t('account360.deals_active')}</span>{' '}
                <span className="font-semibold">{account360.enrichment.active_deal_count}</span>
              </div>
              <div>
                <span className="text-slate-500">{t('account360.deals_won')}</span>{' '}
                <span className="font-semibold">{account360.enrichment.won_deal_count}</span>
              </div>
              <div>
                <span className="text-slate-500">{t('account360.deals_lost')}</span>{' '}
                <span className="font-semibold">{account360.enrichment.lost_deal_count}</span>
              </div>
              <div>
                <span className="text-slate-500">{t('account360.computed')}</span>{' '}
                <span className="font-semibold">
                  {account360.enrichment.computed_at
                    ? formatDate(account360.enrichment.computed_at)
                    : '—'}
                </span>
              </div>
            </div>

            <div className="mt-4 rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2">
              <p className="text-xs font-semibold text-slate-500 uppercase mb-1">
                {t('account360.last_touch')}
              </p>
              <p className="text-sm text-slate-800 dark:text-slate-200">
                {account360.last_touch.summary}
              </p>
              {account360.last_touch.at && (
                <p className="text-xs text-slate-400 mt-1">{formatDate(account360.last_touch.at)}</p>
              )}
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                  {t('account360.risk_block')}
                </p>
                <ul className="list-disc pl-4 text-sm text-slate-700 dark:text-slate-300 space-y-1">
                  {(account360.risk_summary.recommendations || []).slice(0, 4).map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                  {(!account360.risk_summary.recommendations ||
                    account360.risk_summary.recommendations.length === 0) && (
                    <li className="text-slate-400">{t('account360.no_recommendations')}</li>
                  )}
                </ul>
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                  {t('account360.open_deals')}
                </p>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {account360.open_deals.length === 0 ? (
                    <p className="text-sm text-slate-400">{t('account360.no_open_deals')}</p>
                  ) : (
                    account360.open_deals.slice(0, 8).map((o) => (
                      <button
                        key={o.id}
                        type="button"
                        onClick={() => navigate(`/opportunities/${o.id}`)}
                        className="w-full rounded-lg border border-slate-200 dark:border-slate-800 px-2 py-1.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                      >
                        <span className="font-medium text-slate-900 dark:text-white">{o.title}</span>
                        <span className="text-xs text-slate-500 ml-2">{o.stage}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                {t('account360.multi_timeline')}
              </p>
              <div className="max-h-56 overflow-y-auto space-y-2 border border-slate-100 dark:border-slate-800 rounded-lg p-2">
                {account360.timeline.length === 0 ? (
                  <p className="text-sm text-slate-400 py-2">{t('account360.timeline_empty')}</p>
                ) : (
                  account360.timeline.slice(0, 20).map((ev, idx) => (
                    <div
                      key={`${ev.kind}-${idx}-${ev.occurred_at || ''}`}
                      className="text-xs border-b border-slate-100 dark:border-slate-800 pb-2 last:border-0"
                    >
                      <div className="flex justify-between gap-2 text-slate-500">
                        <span>{ev.occurred_at ? formatDate(ev.occurred_at) : '—'}</span>
                        <span className="truncate">
                          {ev.opportunity_title || `#${ev.opportunity_id}`}
                        </span>
                      </div>
                      <p className="text-slate-800 dark:text-slate-200 mt-0.5">
                        <span className="font-medium">{ev.event_type}</span>
                        {ev.description ? ` — ${ev.description}` : ''}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>

            {meetingPrepText && (
              <div className="mt-4 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900 p-3">
                <p className="text-xs font-semibold text-amber-800 dark:text-amber-200 mb-2">
                  {t('account360.meeting_prep_result')}
                </p>
                <pre className="text-sm whitespace-pre-wrap font-sans text-slate-800 dark:text-slate-200">
                  {meetingPrepText}
                </pre>
              </div>
            )}
          </Card>
        ) : null}

        {/* Account Intelligence (v2) */}
        {intelligence && (
          <Card title={t('customer_detail.account_intelligence')}>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                <p className="text-xs text-slate-500">{t('customer_detail.intel_active_opps')}</p>
                <p className="text-lg font-bold text-slate-900 dark:text-white">
                  {intelligence.opportunities.length}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                <p className="text-xs text-slate-500">{t('customer_detail.intel_open_tasks')}</p>
                <p className="text-lg font-bold text-slate-900 dark:text-white">
                  {intelligence.open_tasks_count}
                </p>
              </div>
            </div>

            {intelligence.signals.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                  {t('customer_detail.intel_recent_signals')}
                </p>
                <div className="space-y-2">
                  {intelligence.signals.slice(0, 6).map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => navigate(`/opportunities/${s.opportunity_id}`)}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                          {translateSignalType(s.signal_type, t)}
                        </p>
                        <Badge
                          variant={
                            s.severity === 'high' || s.severity === 'critical'
                              ? 'danger'
                              : s.severity === 'med' || s.severity === 'medium'
                                ? 'warning'
                                : 'default'
                          }
                          size="sm"
                        >
                          {translateSeverity(s.severity, t)}
                        </Badge>
                      </div>
                      {s.evidence && (
                        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                          {s.evidence}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {intelligence.opportunities.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                  {t('customer_detail.intel_opportunities')}
                </p>
                <div className="space-y-2">
                  {intelligence.opportunities.slice(0, 5).map((o) => (
                    <button
                      key={o.id}
                      type="button"
                      onClick={() => navigate(`/opportunities/${o.id}`)}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                          {o.title}
                        </p>
                        <Badge variant="default" size="sm">
                          {translateOpportunityStage(o.stage, t)}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                        {o.amount != null ? formatCurrency(o.amount, o.currency) : '-'}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </Card>
        )}

        {/* AI Customer Summary */}
        <Card title={t('customer_detail.ai_summary_title')}>
          {aiSummaryLoading ? (
            <Skeleton variant="line" count={3} />
          ) : aiSummary ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={14} className="text-honeywell-red" />
                <span className="text-xs text-slate-400">
                  {t('customer_detail.ai_generated_by_claude')}
                </span>
                {aiSummary.cached && (
                  <Badge variant="default" size="sm">
                    {t('customer_detail.cached')}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                {aiSummary.summary}
              </p>
              {aiSummary.sources && aiSummary.sources.length > 0 && (
                <div className="space-y-1 pt-2">
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {t('opp_detail.sources')}
                  </p>
                  <SummarySourceLinks sources={aiSummary.sources} />
                </div>
              )}
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-slate-400">
              {t('customer_detail.ai_summary_empty')}
            </p>
          )}
        </Card>

        <Card
          title={t('opp_detail.changes_title').replace('{{d}}', '7')}
          action={
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => setChangesOpen((s) => !s)}
              >
                {changesOpen ? t('opp_detail.ai_summary_close') : t('opp_detail.changes_show')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                loading={refreshChangesMutation.isPending}
                disabled={!changesOpen}
                onClick={() => refreshChangesMutation.mutate()}
              >
                {t('opp_detail.changes_refresh')}
              </Button>
            </div>
          }
        >
          {aiChangesLoading ? (
            <Skeleton variant="line" count={3} />
          ) : aiChanges && changesOpen ? (
            <div className="space-y-2">
              <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                {aiChanges.summary}
              </p>
              {aiChanges.sources && aiChanges.sources.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {t('opp_detail.sources')}
                  </p>
                  <SummarySourceLinks sources={aiChanges.sources} />
                </div>
              )}
              {aiChanges.generated_at && (
                <p className="text-[10px] text-slate-400">
                  {formatDateTime(aiChanges.generated_at)}
                </p>
              )}
              {aiChanges.cached && (
                <Badge variant="default" size="sm">
                  {t('customer_detail.cached')}
                </Badge>
              )}
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-slate-400">
              {changesOpen ? t('customer_detail.ai_summary_empty') : t('opp_detail.changes_hint')}
            </p>
          )}
        </Card>

        {/* Churn Risk Analysis */}
        <Card title={t('customer_detail.churn_title')}>
          {churnLoading ? (
            <Skeleton variant="line" count={3} />
          ) : churnPrediction?.data ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="flex flex-col items-center">
                  <ShieldAlert
                    size={20}
                    className={
                      churnPrediction.data.risk_level === 'high'
                        ? 'text-red-500'
                        : churnPrediction.data.risk_level === 'medium'
                          ? 'text-amber-500'
                          : 'text-green-500'
                    }
                  />
                  <span className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">
                    %{churnPrediction.data.churn_probability}
                  </span>
                </div>
                <div>
                  <Badge
                    variant={
                      churnPrediction.data.risk_level === 'high'
                        ? 'danger'
                        : churnPrediction.data.risk_level === 'medium'
                          ? 'warning'
                          : 'success'
                    }
                  >
                    {churnPrediction.data.risk_level === 'high'
                      ? t('customer_detail.risk_high')
                      : churnPrediction.data.risk_level === 'medium'
                        ? t('customer_detail.risk_medium')
                        : t('customer_detail.risk_low')}
                  </Badge>
                  <p className="mt-1 text-xs text-slate-500">{t('customer_detail.churn_hint')}</p>
                </div>
              </div>

              {churnPrediction.data.risk_factors &&
                churnPrediction.data.risk_factors.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-slate-500 uppercase">
                      {t('customer_detail.risk_factors')}
                    </h4>
                    {churnPrediction.data.risk_factors.map((rf, i) => (
                      <div key={i} className="rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2">
                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                          {rf.name}
                        </p>
                        <p className="text-xs text-slate-500">{rf.description}</p>
                      </div>
                    ))}
                  </div>
                )}

              {churnPrediction.data.retention_actions &&
                churnPrediction.data.retention_actions.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-slate-500 uppercase mb-1">
                      {t('customer_detail.retention_actions')}
                    </h4>
                    <ul className="space-y-1">
                      {churnPrediction.data.retention_actions.map((action, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
                        >
                          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-honeywell-red" />
                          {action}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-slate-400">
              {t('customer_detail.churn_empty')}
            </p>
          )}
        </Card>

        {/* Inline Opportunities */}
        {oppsData?.items && oppsData.items.length > 0 && (
          <Card
            title={t('customer_detail.opps_title').replace(
              '{count}',
              String(oppsData.items.length),
            )}
          >
            <div className="space-y-2">
              {oppsData.items.map((opp) => (
                <button
                  key={opp.id}
                  type="button"
                  onClick={() => navigate(`/opportunities/${opp.id}`)}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-4 py-3 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800 transition-colors"
                >
                  <div className="min-w-0 text-left">
                    <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                      {opp.title}
                    </p>
                    <p className="text-xs text-slate-500">
                      {translateOpportunityStage(opp.stage, t)} &middot; {opp.status}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge
                      variant={
                        opp.status === 'active'
                          ? 'info'
                          : opp.stage === 'closed_won'
                            ? 'success'
                            : 'default'
                      }
                      size="sm"
                    >
                      {translateOpportunityStage(opp.stage, t)}
                    </Badge>
                    {opp.amount != null && (
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                        {formatCurrency(opp.amount, opp.currency)}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </Card>
        )}

        {/* Quote Summary */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-xl border-l-4 border-l-blue-500 border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-800">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {t('customer_detail.total_quotes')}
              </span>
              <TrendingUp size={16} className="text-blue-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">{quotes.length}</p>
          </div>
          <div className="rounded-xl border-l-4 border-l-red-500 border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-800">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {t('customer_detail.total_value')}
              </span>
              <TrendingUp size={16} className="text-red-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-honeywell-red">
              {formatCurrency(totalValue, 'USD')}
            </p>
          </div>
        </div>

        {/* Quote History */}
        <Card title={t('customer_detail.quote_history')}>
          <DataTable
            columns={quoteColumns}
            data={quotes}
            loading={quotesLoading}
            emptyMessage={t('customer_detail.quotes_empty')}
            onRowClick={(row) => navigate(`/quotes/${(row as Quote).id}`)}
          />
        </Card>

        {/* Customer 360 Timeline */}
        <Card title={t('customer_detail.timeline_card_title')}>
          {timelineData?.events && timelineData.events.length > 0 ? (
            <div className="space-y-0 p-2">
              {timelineData.events.map((event, idx) => (
                <div key={`${event.type}-${event.id}`} className="relative flex gap-3 pb-4">
                  {idx < timelineData.events.length - 1 && (
                    <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-slate-800" />
                  )}
                  <div
                    className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full flex items-center justify-center"
                    style={{
                      backgroundColor: event.type === 'email' ? '#dbeafe' : '#fce7f3',
                    }}
                  >
                    <div
                      className={`h-2.5 w-2.5 rounded-full ${event.type === 'email' ? 'bg-blue-500' : 'bg-pink-500'}`}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          event.type === 'email'
                            ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                            : 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300'
                        }`}
                      >
                        {event.type === 'email'
                          ? t('customer_detail.timeline_email')
                          : t('customer_detail.timeline_quote')}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {formatDate(event.timestamp)}
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm text-slate-900 dark:text-white truncate">
                      {event.title}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                      {event.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-slate-400">
              {t('customer_detail.timeline_empty')}
            </p>
          )}
        </Card>

        {/* Activity Auto-Log Timeline */}
        {activityData?.activities && activityData.activities.length > 0 && (
          <Card title={t('customer_detail.activity_auto_title')}>
            <div className="space-y-0 p-2">
              {activityData.activities.map((activity, idx) => {
                const colorMap: Record<string, string> = {
                  quote_created: 'bg-emerald-500',
                  quote_approved: 'bg-green-500',
                  quote_sent: 'bg-blue-500',
                  email_received: 'bg-indigo-500',
                  email_parsed: 'bg-purple-500',
                  stage_change: 'bg-amber-500',
                  task_created: 'bg-orange-500',
                  task_completed: 'bg-teal-500',
                };
                const dotColor = colorMap[activity.activity_type] || 'bg-gray-400';
                return (
                  <div key={activity.id} className="relative flex gap-3 pb-4">
                    {idx < activityData.activities.length - 1 && (
                      <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-slate-800" />
                    )}
                    <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                      <div className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                          {translateActivityType(activity.activity_type, t)}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {formatDate(activity.created_at)}
                        </span>
                      </div>
                      <p className="mt-0.5 text-sm text-slate-900 dark:text-white truncate">
                        {activity.summary}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {/* Account Hierarchy */}
        {hierarchy && (hierarchy.parents.length > 0 || hierarchy.subsidiaries.length > 0) && (
          <Card>
            <div className="p-4">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3 flex items-center gap-2">
                <Building2 size={16} />
                {t('customer_detail.account_hierarchy')}
              </h3>
              {hierarchy.parents.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-medium text-slate-500 mb-1">
                    {t('customer_detail.parent_accounts')}
                  </p>
                  {hierarchy.parents.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => navigate(`/customers/${p.id}`)}
                      className="block w-full text-left px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded cursor-pointer"
                    >
                      {p.name} {p.company && `(${p.company})`}
                    </button>
                  ))}
                </div>
              )}
              {hierarchy.subsidiaries.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-slate-500 mb-1">
                    {t('customer_detail.subsidiaries_count').replace(
                      '{count}',
                      String(hierarchy.subsidiaries.length),
                    )}
                  </p>
                  {hierarchy.subsidiaries.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => navigate(`/customers/${s.id}`)}
                      className="block w-full text-left px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded cursor-pointer"
                    >
                      {s.name} {s.company && `(${s.company})`}
                    </button>
                  ))}
                  {rollup && (
                    <div className="mt-3 grid grid-cols-2 gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                      <div className="text-center">
                        <p className="text-lg font-bold text-slate-900 dark:text-white">
                          {rollup.total_opportunities}
                        </p>
                        <p className="text-[10px] text-slate-500">
                          {t('customer_detail.total_opps')}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-bold text-slate-900 dark:text-white">
                          {formatCurrency(rollup.total_quote_value)}
                        </p>
                        <p className="text-[10px] text-slate-500">
                          {t('customer_detail.total_quotes')}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </Card>
        )}

        {/* Account Team */}
        <AccountTeamPanel customerId={customerId} />

        {/* Comments */}
        <CommentThread entityType="customer" entityId={customerId} />
      </div>
    </div>
  );
}
