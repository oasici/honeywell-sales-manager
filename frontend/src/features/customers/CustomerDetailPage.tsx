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
import { customersApi, quotesApi, customerHealthApi } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/formatters';
import { STATUS_LABELS, STATUS_COLORS } from '../../lib/constants';
import { Mail, Phone, MapPin, FileText, TrendingUp } from 'lucide-react';
import { HealthScoreCard } from './HealthScoreCard';
import type { Customer, Quote, PaginatedResponse, CustomerHealthReport } from '../../lib/types';

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

  const { data: timelineData } = useQuery<{ events: { type: string; id: number; title: string; detail: string; status: string; timestamp: string }[] }>({
    queryKey: ['customer-timeline', customerId],
    queryFn: () => customersApi.getTimeline(customerId),
    enabled: !!customerId,
  });

  useEffect(() => {
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
  }, [customer]);

  const updateMutation = useMutation({
    mutationFn: (payload: typeof form) =>
      customersApi.updateCustomer(customerId, payload),
    onSuccess: () => {
      toast.success('Musteri guncellendi');
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ['customer', customerId] });
    },
    onError: () => toast.error('Guncelleme basarisiz'),
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
    return (
      <div className="py-16 text-center text-gray-500">Musteri bulunamadi</div>
    );
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
        <span className="font-medium text-sm">
          {formatCurrency(row.grand_total, row.currency)}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Tarih',
      render: (row: Quote) => (
        <span className="text-sm">{formatDate(row.created_at)}</span>
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
            <Button
              loading={updateMutation.isPending}
              onClick={() => updateMutation.mutate(form)}
            >
              Kaydet
            </Button>
          </>
        ) : (
          <Button onClick={() => setEditing(true)}>Duzenle</Button>
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
                  <span className="text-sm text-gray-700 dark:text-gray-300">{customer.email || '-'}</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <Phone size={14} className="shrink-0 text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">{customer.phone || '-'}</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <FileText size={14} className="shrink-0 text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    VKN: {customer.tax_id || '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="shrink-0 text-xs font-bold text-gray-400">
                    {customer.preferred_lang === 'tr' ? 'TR' : customer.preferred_lang === 'en' ? 'EN' : customer.preferred_lang || '-'}
                  </span>
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {customer.preferred_lang === 'tr' ? 'Turkce' : customer.preferred_lang === 'en' ? 'Ingilizce' : 'Dil'}
                  </span>
                </div>
                {customer.address && (
                  <div className="flex items-start gap-2.5 sm:col-span-2">
                    <MapPin size={14} className="mt-0.5 shrink-0 text-gray-400" />
                    <span className="text-sm text-gray-700 dark:text-gray-300">{customer.address}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>

        {/* Health Score — hero position */}
        {healthLoading ? (
          <Skeleton variant="card" />
        ) : healthData ? (
          <HealthScoreCard health={healthData} />
        ) : null}

        {/* Quote Summary */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-xl border-l-4 border-l-blue-500 border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Toplam Teklif
              </span>
              <TrendingUp size={16} className="text-blue-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
              {quotes.length}
            </p>
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
                  <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full flex items-center justify-center" style={{
                    backgroundColor: event.type === 'email' ? '#dbeafe' : '#fce7f3',
                  }}>
                    <div className={`h-2.5 w-2.5 rounded-full ${event.type === 'email' ? 'bg-blue-500' : 'bg-pink-500'}`} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        event.type === 'email' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300'
                      }`}>
                        {event.type === 'email' ? 'Email' : 'Teklif'}
                      </span>
                      <span className="text-[10px] text-gray-400">{formatDate(event.timestamp)}</span>
                    </div>
                    <p className="mt-0.5 text-sm text-gray-900 dark:text-white truncate">{event.title}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{event.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">Henuz etkinlik yok</p>
          )}
        </Card>
      </div>
    </div>
  );
}
