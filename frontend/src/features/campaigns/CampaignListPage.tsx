import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Megaphone, TrendingUp, Wallet, CheckCircle2 } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Modal } from '../../components/ui/Modal';
import { campaignsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { Campaign } from '../../lib/types';
import { STATUS_VARIANTS } from './campaignConstants';
import { useT } from '../../hooks/useT';
import { CAMPAIGN_STATUS_VALUES, translateCampaignStatus } from '../../lib/labelTranslations';

/**
 * KpiTile — KPI summary card (icon + label + tabular-nums value).
 * Tone shifts the value color.
 */
function KpiTile({
  icon,
  label,
  value,
  tone = 'default',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: 'default' | 'positive' | 'negative';
}) {
  const valueClass =
    tone === 'positive'
      ? 'text-emerald-600 dark:text-emerald-400'
      : tone === 'negative'
        ? 'text-red-600 dark:text-red-400'
        : 'text-slate-900 dark:text-white';
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
          {icon}
        </span>
        <p className="text-overline text-slate-500 dark:text-slate-400">{label}</p>
      </div>
      <p
        className={`mt-2.5 text-[22px] font-bold leading-none tracking-tight tabular-nums ${valueClass}`}
      >
        {value}
      </p>
    </div>
  );
}

const TYPE_LABELS: Record<string, string> = {
  email: 'E-posta',
  event: 'Etkinlik',
  webinar: 'Webinar',
  social: 'Sosyal Medya',
  content: 'İçerik',
  other: 'Diğer',
};

const CAMPAIGN_TYPES = [
  { value: 'email', label: 'E-posta' },
  { value: 'event', label: 'Etkinlik' },
  { value: 'webinar', label: 'Webinar' },
  { value: 'social', label: 'Sosyal Medya' },
  { value: 'content', label: 'İçerik' },
  { value: 'other', label: 'Diğer' },
];

interface CreateForm {
  name: string;
  type: string;
  description: string;
  start_date: string;
  end_date: string;
  budget: string;
  // R6-FORM-2 — backend CampaignCreate accepts both. The list page
  // already renders ``campaign.expected_revenue`` (line 311) but the
  // value was always missing for in-app-created campaigns.
  expected_revenue: string;
  status: string;
}

const INITIAL_FORM: CreateForm = {
  name: '',
  type: 'email',
  description: '',
  start_date: '',
  end_date: '',
  budget: '',
  expected_revenue: '',
  status: 'draft',
};

export default function CampaignListPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateForm>(INITIAL_FORM);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['campaigns', statusFilter],
    queryFn: () => campaignsApi.list({ ...(statusFilter ? { status: statusFilter } : {}) }),
  });

  const campaigns: Campaign[] = data?.items ?? [];

  const createMutation = useMutation({
    mutationFn: (payload: Parameters<typeof campaignsApi.create>[0]) =>
      campaignsApi.create(payload),
    onSuccess: (created: Campaign) => {
      toast.success('Kampanya oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      navigate(`/campaigns/${created.id}`);
    },
    onError: () => toast.error('Kampanya oluşturulamadı'),
  });

  const statusTabs = useMemo(
    () => [
      { value: '', label: t('labels.all') },
      ...CAMPAIGN_STATUS_VALUES.map((value) => ({
        value,
        label: translateCampaignStatus(value, t),
      })),
    ],
    [t],
  );

  const handleCreate = useCallback(() => {
    if (!form.name || !form.type) {
      toast.error('Ad ve tip zorunludur');
      return;
    }
    createMutation.mutate({
      name: form.name,
      type: form.type,
      status: form.status || undefined,
      description: form.description || undefined,
      start_date: form.start_date || undefined,
      end_date: form.end_date || undefined,
      budget: form.budget ? parseFloat(form.budget) : undefined,
      expected_revenue: form.expected_revenue ? parseFloat(form.expected_revenue) : undefined,
    });
  }, [form, createMutation]);

  if (isError) {
    return (
      <div>
        {/* R7-I18N-1 — i18n keys now wired. */}
        <PageHeader title={t('campaigns.title')} description={t('campaigns.desc')} />
        <div className="rounded-2xl border border-red-100 bg-red-50/40 p-8 text-center dark:border-red-900/40 dark:bg-red-950/20">
          <p className="text-[14px] font-medium text-red-700 dark:text-red-400">
            {t('campaigns.error_loading')}
          </p>
        </div>
      </div>
    );
  }

  // KPI summary derived from the currently filtered campaigns.
  const summary = useMemo(() => {
    const active = campaigns.filter((c) => c.status === 'active').length;
    const completed = campaigns.filter((c) => c.status === 'completed').length;
    const totalBudget = campaigns.reduce((sum, c) => sum + (c.budget || 0), 0);
    const roiValues = campaigns
      .filter((c) => c.actual_cost > 0)
      .map((c) => ((c.actual_revenue - c.actual_cost) / c.actual_cost) * 100);
    const avgRoi =
      roiValues.length > 0 ? roiValues.reduce((s, v) => s + v, 0) / roiValues.length : null;
    return { active, completed, totalBudget, avgRoi };
  }, [campaigns]);

  return (
    <div>
      <PageHeader title={t('campaigns.title')} description={t('campaigns.desc')}>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Megaphone size={14} />
          {t('campaigns.new')}
        </Button>
      </PageHeader>

      {/* KPI summary strip */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile
          icon={<Megaphone size={14} />}
          label="Aktif Kampanya"
          value={String(summary.active)}
        />
        <KpiTile
          icon={<Wallet size={14} />}
          label="Toplam Bütçe"
          value={formatCurrency(summary.totalBudget)}
        />
        <KpiTile
          icon={<TrendingUp size={14} />}
          label="Ortalama ROI"
          value={
            summary.avgRoi == null
              ? '—'
              : `${summary.avgRoi >= 0 ? '+' : ''}${summary.avgRoi.toFixed(1)}%`
          }
          tone={summary.avgRoi == null ? 'default' : summary.avgRoi >= 0 ? 'positive' : 'negative'}
        />
        <KpiTile
          icon={<CheckCircle2 size={14} />}
          label="Tamamlanan"
          value={String(summary.completed)}
        />
      </div>

      {/* Status segmented tabs */}
      <div
        className="mb-4 inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
        role="tablist"
        aria-label="Kampanya durumu"
      >
        {statusTabs.map((tab) => {
          const isActive = statusFilter === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setStatusFilter(tab.value)}
              className={[
                'inline-flex h-8 items-center rounded-[10px] px-3 text-[13px] font-medium transition-all',
                'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                isActive
                  ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
                  : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
              ].join(' ')}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {isLoading && <Skeleton variant="table" />}

      {!isLoading && campaigns.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<Megaphone size={20} />}
            title="Kampanya bulunamadı"
            description="İlk kampanyanızı oluşturarak başlayın."
            action={
              <Button onClick={() => setIsCreateOpen(true)} variant="secondary">
                <Megaphone size={14} />
                Yeni Kampanya
              </Button>
            }
          />
        </div>
      )}

      {!isLoading && campaigns.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    Kampanya Adı
                  </th>
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    Tip
                  </th>
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    Durum
                  </th>
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    Başlangıç
                  </th>
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    Bitiş
                  </th>
                  <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                    Bütçe
                  </th>
                  <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                    ROI
                  </th>
                  <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                    Üye
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {campaigns.map((campaign) => {
                  const roi =
                    campaign.actual_cost > 0
                      ? ((campaign.actual_revenue - campaign.actual_cost) / campaign.actual_cost) *
                        100
                      : null;
                  return (
                    <tr
                      key={campaign.id}
                      onClick={() => navigate(`/campaigns/${campaign.id}`)}
                      className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-4 py-3 text-[13px] font-semibold text-slate-900 dark:text-white">
                        {/* Description as a tooltip — backend returns
                            it but the table never surfaced it before
                            audit F-19. */}
                        <span title={campaign.description ?? undefined}>{campaign.name}</span>
                        {campaign.expected_revenue != null && campaign.expected_revenue > 0 && (
                          <p className="text-[10px] font-normal text-slate-400">
                            beklenen{' '}
                            {campaign.expected_revenue.toLocaleString('tr-TR', {
                              style: 'currency',
                              currency: 'TRY',
                              maximumFractionDigits: 0,
                            })}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="default" size="sm">
                          {TYPE_LABELS[campaign.type] || campaign.type}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          variant={STATUS_VARIANTS[campaign.status] || 'default'}
                          size="sm"
                          dot
                        >
                          {translateCampaignStatus(campaign.status, t)}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
                        {campaign.start_date
                          ? new Date(campaign.start_date).toLocaleDateString('tr-TR')
                          : '—'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
                        {campaign.end_date
                          ? new Date(campaign.end_date).toLocaleDateString('tr-TR')
                          : '—'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                        {formatCurrency(campaign.budget)}
                      </td>
                      <td
                        className={[
                          'whitespace-nowrap px-4 py-3 text-right text-[13px] font-semibold tabular-nums',
                          roi == null
                            ? 'text-slate-400'
                            : roi >= 0
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400',
                        ].join(' ')}
                      >
                        {roi == null ? '—' : `${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
                        {campaign.member_count ?? '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create Campaign Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          setForm(INITIAL_FORM);
        }}
        title="Yeni Kampanya"
        size="md"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setIsCreateOpen(false);
                setForm(INITIAL_FORM);
              }}
            >
              İptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Oluştur
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Kampanya Adı"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Kampanya adı giriniz"
          />
          <Select
            label="Tip"
            options={CAMPAIGN_TYPES}
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
          />
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
              Açıklama
            </label>
            <textarea
              className="block w-full resize-none rounded-[12px] border border-slate-200 bg-white px-3.5 py-2.5 text-[13px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500"
              rows={3}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Kampanya açıklaması (isteğe bağlı)"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Başlangıç Tarihi"
              type="date"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
            <Input
              label="Bitiş Tarihi"
              type="date"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Bütçe"
              type="number"
              min={0}
              step={0.01}
              value={form.budget}
              onChange={(e) => setForm({ ...form, budget: e.target.value })}
              placeholder="0.00"
            />
            <Input
              label="Beklenen gelir"
              type="number"
              min={0}
              step={0.01}
              value={form.expected_revenue}
              onChange={(e) => setForm({ ...form, expected_revenue: e.target.value })}
              placeholder="0.00"
            />
          </div>
          <Select
            label="Durum"
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
            options={CAMPAIGN_STATUS_VALUES.map((value) => ({
              value,
              label: translateCampaignStatus(value, t),
            }))}
          />
        </div>
      </Modal>
    </div>
  );
}
