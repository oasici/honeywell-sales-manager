import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { campaignsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { Modal } from '../../components/ui/Modal';
import type { Campaign } from '../../lib/types';
import { Megaphone } from 'lucide-react';
import { STATUS_LABELS, STATUS_VARIANTS } from './campaignConstants';

const STATUS_TABS = [
  { value: '', label: 'Tumu' },
  { value: 'draft', label: 'Taslak' },
  { value: 'active', label: 'Aktif' },
  { value: 'paused', label: 'Durduruldu' },
  { value: 'completed', label: 'Tamamlandi' },
];

const TYPE_LABELS: Record<string, string> = {
  email: 'E-posta',
  event: 'Etkinlik',
  webinar: 'Webinar',
  social: 'Sosyal Medya',
  content: 'Icerik',
  other: 'Diger',
};

const CAMPAIGN_TYPES = [
  { value: 'email', label: 'E-posta' },
  { value: 'event', label: 'Etkinlik' },
  { value: 'webinar', label: 'Webinar' },
  { value: 'social', label: 'Sosyal Medya' },
  { value: 'content', label: 'Icerik' },
  { value: 'other', label: 'Diger' },
];

interface CreateForm {
  name: string;
  type: string;
  description: string;
  start_date: string;
  end_date: string;
  budget: string;
}

const INITIAL_FORM: CreateForm = {
  name: '',
  type: 'email',
  description: '',
  start_date: '',
  end_date: '',
  budget: '',
};

export default function CampaignListPage() {
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
      toast.success('Kampanya olusturuldu');
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      navigate(`/campaigns/${created.id}`);
    },
    onError: () => toast.error('Kampanya olusturulamadi'),
  });

  const handleCreate = useCallback(() => {
    if (!form.name || !form.type) {
      toast.error('Ad ve tip zorunludur');
      return;
    }
    createMutation.mutate({
      name: form.name,
      type: form.type,
      description: form.description || undefined,
      start_date: form.start_date || undefined,
      end_date: form.end_date || undefined,
      budget: form.budget ? parseFloat(form.budget) : undefined,
    });
  }, [form, createMutation]);

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Kampanyalar" description="Kampanya yonetimi ve ROI takibi" />
        <Card>
          <div className="p-8 text-center">
            <p className="text-sm text-red-500">
              Veriler yuklenirken bir hata olustu. Lutfen sayfayi yenileyin.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Kampanyalar" description="Kampanya yonetimi ve ROI takibi">
        <Button onClick={() => setIsCreateOpen(true)}>
          <Megaphone className="mr-1.5 h-4 w-4" />
          Yeni Kampanya
        </Button>
      </PageHeader>

      {/* Status filter tabs */}
      <div className="mb-4 flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => setStatusFilter(tab.value)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              statusFilter === tab.value
                ? 'bg-honeywell-red text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton variant="card" count={3} />}

      {!isLoading && campaigns.length === 0 && (
        <Card>
          <p className="py-8 text-center text-sm text-gray-500">Kampanya bulunamadi</p>
        </Card>
      )}

      {!isLoading && campaigns.length > 0 && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Kampanya Adi</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Tip</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Durum</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Baslangic</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Bitis</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    Butce
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    ROI %
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">Uye</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((campaign) => {
                  const roiPct =
                    campaign.actual_cost > 0
                      ? (
                          ((campaign.actual_revenue - campaign.actual_cost) /
                            campaign.actual_cost) *
                          100
                        ).toFixed(1)
                      : '-';
                  return (
                    <tr
                      key={campaign.id}
                      onClick={() => navigate(`/campaigns/${campaign.id}`)}
                      className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors dark:border-gray-700 dark:hover:bg-gray-800/40"
                    >
                      <td className="px-3 py-2 font-medium text-gray-900 dark:text-white">
                        {campaign.name}
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant="default">
                          {TYPE_LABELS[campaign.type] || campaign.type}
                        </Badge>
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant={STATUS_VARIANTS[campaign.status] || 'default'}>
                          {STATUS_LABELS[campaign.status] || campaign.status}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                        {campaign.start_date
                          ? new Date(campaign.start_date).toLocaleDateString('tr-TR')
                          : '-'}
                      </td>
                      <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                        {campaign.end_date
                          ? new Date(campaign.end_date).toLocaleDateString('tr-TR')
                          : '-'}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-900 dark:text-white">
                        {formatCurrency(campaign.budget)}
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-gray-900 dark:text-white">
                        {roiPct !== '-' ? `${roiPct}%` : '-'}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                        {campaign.member_count ?? '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create Campaign Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          setForm(INITIAL_FORM);
        }}
        title="Yeni Kampanya"
      >
        <div className="space-y-3">
          <Input
            label="Kampanya Adi"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Kampanya adi giriniz"
          />
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Tip
            </label>
            <select
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              {CAMPAIGN_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Aciklama
            </label>
            <textarea
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400 focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              rows={2}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Kampanya aciklamasi (isteğe bagli)"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Baslangic Tarihi"
              type="date"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
            <Input
              label="Bitis Tarihi"
              type="date"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </div>
          <Input
            label="Butce"
            type="number"
            min={0}
            step={0.01}
            value={form.budget}
            onChange={(e) => setForm({ ...form, budget: e.target.value })}
            placeholder="0.00"
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setIsCreateOpen(false);
              setForm(INITIAL_FORM);
            }}
          >
            Iptal
          </Button>
          <Button onClick={handleCreate} loading={createMutation.isPending}>
            Olustur
          </Button>
        </div>
      </Modal>
    </div>
  );
}
