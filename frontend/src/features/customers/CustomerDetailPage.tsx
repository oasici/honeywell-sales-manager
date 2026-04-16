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
import { formatCurrency, formatDate } from '../../lib/formatters';
import { STATUS_LABELS, STATUS_COLORS } from '../../lib/constants';
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
} from 'lucide-react';
import { Badge } from '../../components/ui/Badge';
import { HealthScoreCard } from './HealthScoreCard';
import AccountTeamPanel from './AccountTeamPanel';
import CommentThread from '../board/CommentThread';
import type {
  Customer,
  Quote,
  PaginatedResponse,
  CustomerHealthReport,
  AiSummarizeResponse,
  Opportunity,
  ChurnPredictionResult,
} from '../../lib/types';

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const customerId = Number(id);

  const [editing, setEditing] = useState(false);
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
      toast.success('Musteri guncellendi');
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ['customer', customerId] });
    },
    onError: () => toast.error('Guncelleme basarisiz'),
  });

  const enrichMutation = useMutation({
    mutationFn: () => customersApi.enrich(customerId),
    onSuccess: () => {
      toast.success('Musteri verileri zenginlestirildi');
      queryClient.invalidateQueries({ queryKey: ['customer', customerId] });
    },
    onError: () => toast.error('Zenginlestirme basarisiz'),
  });

  const updateField = (field: string, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="card" count={2} />
      </div>
    );
  }

  if (!customer) {
    return <div className="py-16 text-center text-gray-500">Musteri bulunamadi</div>;
  }

  const quotes = quotesData?.items || [];
  const totalValue = quotes.reduce((sum, q) => sum + q.grand_total, 0);

  const quoteColumns = [
    {
      key: 'quote_number',
      header: 'Teklif No',
      render: (row: Quote) => (
        <button
          type="button"
          onClick={() => navigate(`/quotes/${row.id}`)}
          className="font-semibold text-honeywell-red hover:underline"
        >
          {row.quote_number}
        </button>
      ),
    },
    {
      key: 'status',
      header: 'Durum',
      render: (row: Quote) => (
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            STATUS_COLORS[row.status] || 'bg-gray-100 text-gray-700'
          }`}
        >
          {STATUS_LABELS[row.status] || row.status}
        </span>
      ),
    },
    {
      key: 'grand_total',
      header: 'Toplam',
      render: (row: Quote) => (
        <span className="font-medium text-sm">{formatCurrency(row.grand_total, row.currency)}</span>
      ),
    },
    {
      key: 'created_at',
      header: 'Tarih',
      render: (row: Quote) => <span className="text-sm">{formatDate(row.created_at)}</span>,
    },
  ];

  return (
    <div>
      <PageHeader
        title={customer.company || customer.name}
        description={customer.company ? customer.name : undefined}
      >
        <Button variant="secondary" onClick={() => navigate('/customers')}>
          Geri Don
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
              Iptal
            </Button>
            <Button loading={updateMutation.isPending} onClick={() => updateMutation.mutate(form)}>
              Kaydet
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
              Zenginlestir
            </Button>
            <Button onClick={() => setEditing(true)}>Duzenle</Button>
          </>
        )}
      </PageHeader>

      <div className="space-y-6">
        {/* Customer Info */}
        <Card title="Musteri Bilgileri">
          {editing ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input
                label="Isim"
                value={form.name}
                onChange={(e) => updateField('name', e.target.value)}
                required
              />
              <Input
                label="Sirket"
                value={form.company}
                onChange={(e) => updateField('company', e.target.value)}
              />
              <Input
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => updateField('email', e.target.value)}
                required
              />
              <Input
                label="Telefon"
                value={form.phone}
                onChange={(e) => updateField('phone', e.target.value)}
              />
              <Input
                label="Vergi No"
                value={form.tax_id}
                onChange={(e) => updateField('tax_id', e.target.value)}
              />
              <Input
                label="Tercih Edilen Dil"
                value={form.preferred_lang}
                onChange={(e) => updateField('preferred_lang', e.target.value)}
                placeholder="tr / en"
              />
              <div className="sm:col-span-2">
                <Input
                  label="Adres"
                  value={form.address}
                  onChange={(e) => updateField('address', e.target.value)}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Customer hero */}
              <div>
                <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                  {customer.company || customer.name}
                </h3>
                {customer.company && (
                  <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">{customer.name}</p>
                )}
              </div>

              {/* Contact info with icons */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex items-center gap-2.5">
                  <Mail size={14} className="shrink-0 text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {customer.email || '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <Phone size={14} className="shrink-0 text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {customer.phone || '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <FileText size={14} className="shrink-0 text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    VKN: {customer.tax_id || '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="shrink-0 text-xs font-bold text-gray-400">
                    {customer.preferred_lang === 'tr'
                      ? 'TR'
                      : customer.preferred_lang === 'en'
                        ? 'EN'
                        : customer.preferred_lang || '-'}
                  </span>
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {customer.preferred_lang === 'tr'
                      ? 'Turkce'
                      : customer.preferred_lang === 'en'
                        ? 'Ingilizce'
                        : 'Dil'}
                  </span>
                </div>
                {customer.address && (
                  <div className="flex items-start gap-2.5 sm:col-span-2">
                    <MapPin size={14} className="mt-0.5 shrink-0 text-gray-400" />
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {customer.address}
                    </span>
                  </div>
                )}
              </div>

              {/* Enrichment data */}
              {customer.enriched_at && (
                <div className="mt-4 space-y-3 border-t border-gray-200 pt-4 dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    <Sparkles size={14} className="text-honeywell-red" />
                    <Badge variant="info" size="sm">
                      AI Zenginlestirildi
                    </Badge>
                    <span className="text-[10px] text-gray-400">
                      {formatDate(customer.enriched_at)}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {customer.industry && (
                      <div className="flex items-center gap-2.5">
                        <Building2 size={14} className="shrink-0 text-gray-400" />
                        <Badge variant="default" size="sm">
                          {customer.industry}
                        </Badge>
                      </div>
                    )}
                    {customer.employee_count != null && (
                      <div className="flex items-center gap-2.5">
                        <Users size={14} className="shrink-0 text-gray-400" />
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {customer.employee_count.toLocaleString()} calisan
                        </span>
                      </div>
                    )}
                    {customer.annual_revenue && (
                      <div className="flex items-center gap-2.5">
                        <TrendingUp size={14} className="shrink-0 text-gray-400" />
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {customer.annual_revenue}
                        </span>
                      </div>
                    )}
                    {customer.website && (
                      <div className="flex items-center gap-2.5">
                        <Globe size={14} className="shrink-0 text-gray-400" />
                        <a
                          href={customer.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-honeywell-red hover:underline"
                        >
                          {customer.website}
                        </a>
                      </div>
                    )}
                    {customer.linkedin_url && (
                      <div className="flex items-center gap-2.5">
                        <ExternalLink size={14} className="shrink-0 text-gray-400" />
                        <a
                          href={customer.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-honeywell-red hover:underline"
                        >
                          LinkedIn
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

        {/* AI Customer Summary */}
        <Card title="AI Musteri Ozeti">
          {aiSummaryLoading ? (
            <Skeleton variant="line" count={3} />
          ) : aiSummary ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={14} className="text-honeywell-red" />
                <span className="text-xs text-gray-400">Claude AI tarafindan olusturuldu</span>
                {aiSummary.cached && (
                  <Badge variant="default" size="sm">
                    Onbellek
                  </Badge>
                )}
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                {aiSummary.summary}
              </p>
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-gray-400">AI ozet bulunamadi</p>
          )}
        </Card>

        {/* Churn Risk Analysis */}
        <Card title="Kayip Risk Analizi">
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
                  <span className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
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
                      ? 'Yuksek Risk'
                      : churnPrediction.data.risk_level === 'medium'
                        ? 'Orta Risk'
                        : 'Dusuk Risk'}
                  </Badge>
                  <p className="mt-1 text-xs text-gray-500">Kayip olasiligi tahmini</p>
                </div>
              </div>

              {churnPrediction.data.risk_factors &&
                churnPrediction.data.risk_factors.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-gray-500 uppercase">
                      Risk Faktorleri
                    </h4>
                    {churnPrediction.data.risk_factors.map((rf, i) => (
                      <div key={i} className="rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2">
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {rf.name}
                        </p>
                        <p className="text-xs text-gray-500">{rf.description}</p>
                      </div>
                    ))}
                  </div>
                )}

              {churnPrediction.data.retention_actions &&
                churnPrediction.data.retention_actions.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                      Elde Tutma Aksiyonlari
                    </h4>
                    <ul className="space-y-1">
                      {churnPrediction.data.retention_actions.map((action, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400"
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
            <p className="py-4 text-center text-sm text-gray-400">Kayip risk verisi bulunamadi</p>
          )}
        </Card>

        {/* Inline Opportunities */}
        {oppsData?.items && oppsData.items.length > 0 && (
          <Card title={`Firsatlar (${oppsData.items.length})`}>
            <div className="space-y-2">
              {oppsData.items.map((opp) => (
                <button
                  key={opp.id}
                  type="button"
                  onClick={() => navigate(`/opportunities/${opp.id}`)}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800 transition-colors"
                >
                  <div className="min-w-0 text-left">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                      {opp.title}
                    </p>
                    <p className="text-xs text-gray-500">
                      {opp.stage} &middot; {opp.status}
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
                      {opp.stage}
                    </Badge>
                    {opp.amount != null && (
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
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
          <div className="rounded-xl border-l-4 border-l-blue-500 border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Toplam Teklif
              </span>
              <TrendingUp size={16} className="text-blue-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{quotes.length}</p>
          </div>
          <div className="rounded-xl border-l-4 border-l-red-500 border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Toplam Deger
              </span>
              <TrendingUp size={16} className="text-red-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-honeywell-red">
              {formatCurrency(totalValue, 'USD')}
            </p>
          </div>
        </div>

        {/* Quote History */}
        <Card title="Teklif Gecmisi">
          <DataTable
            columns={quoteColumns}
            data={quotes}
            loading={quotesLoading}
            emptyMessage="Bu musteriye ait teklif bulunamadi"
            onRowClick={(row) => navigate(`/quotes/${(row as Quote).id}`)}
          />
        </Card>

        {/* Customer 360 Timeline */}
        <Card title="Musteri Zaman Cizelgesi">
          {timelineData?.events && timelineData.events.length > 0 ? (
            <div className="space-y-0 p-2">
              {timelineData.events.map((event, idx) => (
                <div key={`${event.type}-${event.id}`} className="relative flex gap-3 pb-4">
                  {idx < timelineData.events.length - 1 && (
                    <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-gray-700" />
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
                        {event.type === 'email' ? 'Email' : 'Teklif'}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {formatDate(event.timestamp)}
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm text-gray-900 dark:text-white truncate">
                      {event.title}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {event.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">Henuz etkinlik yok</p>
          )}
        </Card>

        {/* Activity Auto-Log Timeline */}
        {activityData?.activities && activityData.activities.length > 0 && (
          <Card title="Aktivite Gecmisi (Otomatik)">
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
                      <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-gray-700" />
                    )}
                    <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                      <div className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:text-gray-300">
                          {activity.activity_type.replace(/_/g, ' ')}
                        </span>
                        <span className="text-[10px] text-gray-400">
                          {formatDate(activity.created_at)}
                        </span>
                      </div>
                      <p className="mt-0.5 text-sm text-gray-900 dark:text-white truncate">
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
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Building2 size={16} />
                Hesap Hiyerarsisi
              </h3>
              {hierarchy.parents.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-medium text-gray-500 mb-1">Ust Hesaplar</p>
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
                  <p className="text-xs font-medium text-gray-500 mb-1">
                    Alt Hesaplar ({hierarchy.subsidiaries.length})
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
                    <div className="mt-3 grid grid-cols-2 gap-2 pt-3 border-t border-gray-100 dark:border-gray-800">
                      <div className="text-center">
                        <p className="text-lg font-bold text-gray-900 dark:text-white">
                          {rollup.total_opportunities}
                        </p>
                        <p className="text-[10px] text-gray-500">Toplam Firsat</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-bold text-gray-900 dark:text-white">
                          {formatCurrency(rollup.total_quote_value)}
                        </p>
                        <p className="text-[10px] text-gray-500">Toplam Teklif</p>
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
