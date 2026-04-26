import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Users, Plus, Target, Clock, TrendingUp } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { engagementApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import type { Segment } from '../../lib/types';
import { useT } from '../../hooks/useT';

interface SegmentCustomer {
  id: number;
  name: string;
  company: string;
  email: string;
}

interface SegmentCustomersResponse {
  segment_id: number;
  segment_name: string;
  customers: SegmentCustomer[];
}

export default function SegmentsPage() {
  const t = useT();
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedSegmentId, setSelectedSegmentId] = useState<number | null>(null);

  const [form, setForm] = useState({
    name: '',
    description: '',
    rulesJson: '[]',
  });

  const { data, isLoading } = useQuery<{ segments: Segment[] }>({
    queryKey: ['segments'],
    queryFn: () => engagementApi.listSegments(),
  });

  const customersQuery = useQuery<SegmentCustomersResponse>({
    queryKey: ['segment-customers', selectedSegmentId],
    queryFn: () => engagementApi.getSegmentCustomers(selectedSegmentId!),
    enabled: selectedSegmentId !== null,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => engagementApi.createSegment(payload),
    onSuccess: () => {
      toast.success(t('segments.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['segments'] });
      setIsCreateOpen(false);
      resetForm();
    },
    onError: () => toast.error(t('segments.toast_create_fail')),
  });

  function resetForm() {
    setForm({ name: '', description: '', rulesJson: '[]' });
  }

  function handleCreate() {
    if (!form.name.trim()) {
      toast.error(t('segments.err_name_required'));
      return;
    }
    let rules: unknown[];
    try {
      rules = JSON.parse(form.rulesJson);
    } catch {
      toast.error(t('segments.err_json'));
      return;
    }
    createMutation.mutate({
      name: form.name,
      ...(form.description && { description: form.description }),
      rules,
    });
  }

  const segments = data?.segments ?? [];

  /**
   * Pre-baked segment templates surfaced in the empty state.
   *
   * Each template ships with a `rules` array that mirrors the JSON the
   * backend expects, so clicking "Bu şablonu kullan" pre-populates the
   * create form. Keeps the empty state from feeling like a dead-end.
   */
  const SEGMENT_TEMPLATES: Array<{
    icon: React.ReactNode;
    title: string;
    description: string;
    rules: Record<string, unknown>[];
  }> = [
    {
      icon: <Target size={16} />,
      title: 'Yüksek niyetli müşteriler',
      description: 'Health skoru ≥ 80 ve son 14 günde aktivite kaydı olan hesaplar.',
      rules: [
        { field: 'health_score', operator: 'gte', value: 80 },
        { field: 'last_activity_days', operator: 'lte', value: 14 },
      ],
    },
    {
      icon: <Clock size={16} />,
      title: 'Son 30 gün aktivitesi olmayanlar',
      description: 'Bir aydan uzun süredir kontak kurulmamış ve risk altına giren hesaplar.',
      rules: [{ field: 'last_activity_days', operator: 'gt', value: 30 }],
    },
    {
      icon: <TrendingUp size={16} />,
      title: 'Teklif değeri yüksek hesaplar',
      description: 'Toplam açık teklif değeri 100.000 TRY üzerindeki müşteriler.',
      rules: [{ field: 'total_quote_value', operator: 'gt', value: 100000 }],
    },
  ];

  function applyTemplate(tpl: (typeof SEGMENT_TEMPLATES)[number]) {
    setForm({
      name: tpl.title,
      description: tpl.description,
      rulesJson: JSON.stringify(tpl.rules, null, 2),
    });
    setIsCreateOpen(true);
  }

  return (
    <div>
      <PageHeader title={t('segments.title')} description={t('segments.description')}>
        {/* Segment listesi doluyken üst-sağda CTA gösteriyoruz; empty
            state'te kendi CTA'sı olduğu için burada gizliyoruz, böylece
            iki CTA çakışmıyor. */}
        {segments.length > 0 && (
          <Button onClick={() => setIsCreateOpen(true)}>
            <Plus size={14} />
            {t('segments.btn_new')}
          </Button>
        )}
      </PageHeader>

      {isLoading ? (
        <Skeleton variant="card" count={3} />
      ) : segments.length === 0 ? (
        // Template-driven empty state — three example segment cards make
        // the "neye benzer" sorusunu yanıtlıyor; "İlk Segmenti Oluştur"
        // primary CTA boş şablonla giriyor.
        <div className="space-y-6">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
            <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
              <span className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                <Users size={24} />
              </span>
              <h3 className="text-heading-3 text-slate-900 dark:text-white">
                Hadi ilk segmentinizi oluşturalım
              </h3>
              <p className="mt-1.5 max-w-[460px] text-[13px] text-slate-500 dark:text-slate-400">
                Aşağıdaki hazır şablonlardan biriyle başlayın ya da sıfırdan kendi kuralınızı
                tanımlayın.
              </p>
              <div className="mt-5">
                <Button onClick={() => setIsCreateOpen(true)}>
                  <Plus size={14} />
                  {t('segments.first_add')}
                </Button>
              </div>
            </div>
          </div>

          <div>
            <p className="mb-3 text-overline text-slate-500 dark:text-slate-400">Hızlı şablonlar</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {SEGMENT_TEMPLATES.map((tpl) => (
                <button
                  key={tpl.title}
                  type="button"
                  onClick={() => applyTemplate(tpl)}
                  className="group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-800 dark:bg-slate-900"
                >
                  <span className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 group-hover:bg-honeywell-red/10 group-hover:text-honeywell-red group-hover:ring-honeywell-red/20 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                    {tpl.icon}
                  </span>
                  <h4 className="text-[14px] font-semibold text-slate-900 dark:text-white">
                    {tpl.title}
                  </h4>
                  <p className="mt-1.5 text-[12px] leading-5 text-slate-500 dark:text-slate-400">
                    {tpl.description}
                  </p>
                  <span className="mt-3 inline-flex items-center gap-1 text-[12px] font-medium text-honeywell-red">
                    Bu şablonu kullan →
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {segments.map((segment) => (
            <button
              key={segment.id}
              type="button"
              className="w-full text-left"
              onClick={() => setSelectedSegmentId(segment.id)}
            >
              <Card>
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-slate-900">{segment.name}</h4>
                  {segment.description && (
                    <p className="text-sm text-slate-600 line-clamp-2">{segment.description}</p>
                  )}
                  <div className="flex items-center gap-3">
                    <Badge variant="info" size="sm">
                      {t('segments.customer_count').replace(
                        '{count}',
                        String(segment.customer_count),
                      )}
                    </Badge>
                    <span className="text-xs text-slate-500">
                      {formatDateTime(segment.created_at)}
                    </span>
                  </div>
                </div>
              </Card>
            </button>
          ))}
        </div>
      )}

      {/* Segment Customers Modal */}
      <Modal
        isOpen={selectedSegmentId !== null}
        onClose={() => setSelectedSegmentId(null)}
        title={customersQuery.data?.segment_name ?? t('segments.modal_customers_fallback_title')}
        size="lg"
      >
        {customersQuery.isLoading ? (
          <Skeleton variant="table" />
        ) : !customersQuery.data?.customers?.length ? (
          <EmptyState
            title={t('segments.no_customers_title')}
            description={t('segments.no_customers_desc')}
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th
                    scope="col"
                    className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500"
                  >
                    {t('segments.customers_col_name')}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500"
                  >
                    {t('segments.customers_col_company')}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500"
                  >
                    {t('segments.customers_col_email')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {customersQuery.data.customers.map((customer) => (
                  <tr key={customer.id} className="border-b border-slate-100 last:border-b-0">
                    <td className="px-4 py-3 font-medium text-slate-900">{customer.name}</td>
                    <td className="px-4 py-3 text-slate-600">{customer.company || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{customer.email}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      {/* Create Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title={t('segments.modal_create_title')}
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              {t('segments.lbl_name')}
            </label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Örneğin: Yüksek Degerli Müşteriler"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              {t('segments.lbl_description')}
            </label>
            <Input
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder={t('segments.ph_desc')}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              {t('segments.lbl_rules_json')}
            </label>
            <textarea
              className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              rows={6}
              value={form.rulesJson}
              onChange={(e) => setForm((f) => ({ ...f, rulesJson: e.target.value }))}
              placeholder='[{"field": "total_quote_value", "operator": "gt", "value": 10000}]'
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button loading={createMutation.isPending} onClick={handleCreate}>
              {t('common.create')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
