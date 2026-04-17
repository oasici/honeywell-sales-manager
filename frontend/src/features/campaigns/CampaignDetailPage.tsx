import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { campaignsApi, leadsApi, customersApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { Modal } from '../../components/ui/Modal';
import type { Campaign, CampaignMember, CampaignROI, Customer } from '../../lib/types';
import { Pencil, Trash2, UserPlus } from 'lucide-react';
import { STATUS_LABELS, STATUS_VARIANTS } from './campaignConstants';

const TYPE_LABELS: Record<string, string> = {
  email: 'E-posta',
  event: 'Etkinlik',
  webinar: 'Webinar',
  social: 'Sosyal Medya',
  content: 'İçerik',
  other: 'Diğer',
};

const MEMBER_STATUS_OPTIONS = [
  { value: 'sent', label: 'Gönderildi' },
  { value: 'opened', label: 'Acildi' },
  { value: 'clicked', label: 'Tiklandi' },
  { value: 'responded', label: 'Yanit Verdi' },
  { value: 'converted', label: 'Donusturuldu' },
  { value: 'unsubscribed', label: 'Abonelik Iptali' },
];

function KpiCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const campaignId = Number(id);

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isAddMembersOpen, setIsAddMembersOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [memberSearch, setMemberSearch] = useState('');
  const [memberType, setMemberType] = useState<'lead' | 'customer'>('customer');
  const [editForm, setEditForm] = useState<Partial<Campaign>>({});

  const { data: campaign, isLoading } = useQuery<Campaign>({
    queryKey: ['campaign', campaignId],
    queryFn: () => campaignsApi.get(campaignId),
    enabled: !!campaignId,
  });

  const { data: roi } = useQuery<CampaignROI>({
    queryKey: ['campaign-roi', campaignId],
    queryFn: () => campaignsApi.getRoi(campaignId),
    enabled: !!campaignId,
  });

  const { data: membersData, isLoading: membersLoading } = useQuery({
    queryKey: ['campaign-members', campaignId],
    queryFn: () => campaignsApi.getMembers(campaignId, { limit: 100 }),
    enabled: !!campaignId,
  });

  const members: CampaignMember[] = membersData?.items ?? [];

  type SearchItem =
    | Customer
    | { id: number; first_name: string; last_name: string; email?: string };
  const { data: customerResults } = useQuery<{ items: SearchItem[] }>({
    queryKey: ['customers-search', memberSearch, memberType],
    queryFn: () =>
      memberType === 'customer'
        ? customersApi.getCustomers({ search: memberSearch, page_size: 10 })
        : leadsApi.list({ q: memberSearch, page_size: 10 }),
    enabled: memberSearch.length >= 2,
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => campaignsApi.update(campaignId, payload),
    onSuccess: () => {
      toast.success('Kampanya guncellendi');
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId] });
      setIsEditOpen(false);
    },
    onError: () => toast.error('Güncelleme başarısız'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => campaignsApi.delete(campaignId),
    onSuccess: () => {
      toast.success('Kampanya silindi');
      navigate('/campaigns');
    },
    onError: () => toast.error('Silme başarısız'),
  });

  const addMembersMutation = useMutation({
    mutationFn: (members: Array<{ lead_id?: number; customer_id?: number }>) =>
      campaignsApi.addMembers(campaignId, members),
    onSuccess: () => {
      toast.success('Üye eklendi');
      queryClient.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId] });
      setIsAddMembersOpen(false);
      setMemberSearch('');
    },
    onError: () => toast.error('Üye eklenemedi'),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: number) => campaignsApi.removeMember(campaignId, memberId),
    onSuccess: () => {
      toast.success('Üye kaldırıldı');
      queryClient.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
    },
    onError: () => toast.error('Üye kaldirilmadi'),
  });

  const updateMemberStatusMutation = useMutation({
    mutationFn: ({ memberId, status }: { memberId: number; status: string }) =>
      campaignsApi.updateMemberStatus(campaignId, memberId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
    },
    onError: () => toast.error('Durum guncellenemedi'),
  });

  const handleOpenEdit = useCallback(() => {
    if (campaign) {
      setEditForm({
        name: campaign.name,
        type: campaign.type,
        status: campaign.status,
        description: campaign.description,
        start_date: campaign.start_date,
        end_date: campaign.end_date,
        budget: campaign.budget,
      });
      setIsEditOpen(true);
    }
  }, [campaign]);

  const handleAddMember = useCallback(
    (item: { id: number }) => {
      if (memberType === 'customer') {
        addMembersMutation.mutate([{ customer_id: item.id }]);
      } else {
        addMembersMutation.mutate([{ lead_id: item.id }]);
      }
    },
    [memberType, addMembersMutation],
  );

  if (isLoading) {
    return <Skeleton variant="card" count={4} />;
  }

  if (!campaign) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-gray-500">Kampanya bulunamadi</p>
        <Button variant="secondary" onClick={() => navigate('/campaigns')} className="mt-4">
          Geri Don
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={campaign.name} description="Kampanya detaylari ve analitik">
        <Badge variant={STATUS_VARIANTS[campaign.status] || 'default'}>
          {STATUS_LABELS[campaign.status] || campaign.status}
        </Badge>
        <Button variant="secondary" onClick={() => navigate('/campaigns')}>
          Geri Don
        </Button>
        <Button variant="secondary" onClick={handleOpenEdit}>
          <Pencil className="mr-1.5 h-4 w-4" />
          Düzenle
        </Button>
        <Button
          variant="danger"
          onClick={() => setIsDeleteOpen(true)}
          loading={deleteMutation.isPending}
        >
          <Trash2 className="mr-1.5 h-4 w-4" />
          Sil
        </Button>
      </PageHeader>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <KpiCard
          label="Gercek Maliyet"
          value={formatCurrency(roi?.actual_cost ?? campaign.actual_cost)}
        />
        <KpiCard
          label="Gercek Gelir"
          value={formatCurrency(roi?.actual_revenue ?? campaign.actual_revenue)}
        />
        <KpiCard
          label="ROI"
          value={roi ? `${roi.roi_pct.toFixed(1)}%` : '-'}
          sub={roi ? `${roi.member_count} uye` : undefined}
        />
        <KpiCard
          label="Donusum Orani"
          value={roi ? `${roi.conversion_rate.toFixed(1)}%` : '-'}
          sub={roi ? `${roi.responded_count} yanit` : undefined}
        />
      </div>

      {/* Campaign Info */}
      <Card title="Kampanya Bilgileri">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-xs text-gray-500">Tip</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {TYPE_LABELS[campaign.type] || campaign.type}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Durum</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {STATUS_LABELS[campaign.status] || campaign.status}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Baslangic</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {campaign.start_date
                ? new Date(campaign.start_date).toLocaleDateString('tr-TR')
                : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Bitis</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {campaign.end_date ? new Date(campaign.end_date).toLocaleDateString('tr-TR') : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Butce</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {formatCurrency(campaign.budget)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Beklenen Gelir</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {formatCurrency(campaign.expected_revenue)}
            </p>
          </div>
          {campaign.description && (
            <div className="col-span-full">
              <p className="text-xs text-gray-500">Açıklama</p>
              <p className="text-sm text-gray-700 dark:text-gray-300">{campaign.description}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Members Section */}
      <Card title={`Uyeler (${members.length})`}>
        <div className="mb-3 flex justify-end">
          <Button onClick={() => setIsAddMembersOpen(true)}>
            <UserPlus className="mr-1.5 h-4 w-4" />
            Üye Ekle
          </Button>
        </div>

        {membersLoading && <Skeleton variant="table" count={3} />}

        {!membersLoading && members.length === 0 && (
          <p className="py-6 text-center text-sm text-gray-400">Henüz üye eklenmedi</p>
        )}

        {!membersLoading && members.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Ad / Firma</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Tip</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Email</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Durum</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">Eklendi</th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500" />
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  const name = member.lead
                    ? `${member.lead.first_name} ${member.lead.last_name}`
                    : (member.customer?.name ?? '-');
                  const email = member.lead?.email ?? member.customer?.email ?? '-';
                  const isLead = !!member.lead_id;

                  return (
                    <tr key={member.id} className="border-b border-gray-100 dark:border-gray-700">
                      <td className="px-3 py-2 font-medium text-gray-900 dark:text-white">
                        {name}
                        {member.customer?.company && (
                          <span className="ml-1.5 text-xs text-gray-400">
                            {member.customer.company}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant={isLead ? 'warning' : 'info'}>
                          {isLead ? 'Lead' : 'Müşteri'}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-gray-600 dark:text-gray-400">{email}</td>
                      <td className="px-3 py-2">
                        <select
                          className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                          value={member.status}
                          onChange={(e) =>
                            updateMemberStatusMutation.mutate({
                              memberId: member.id,
                              status: e.target.value,
                            })
                          }
                        >
                          {MEMBER_STATUS_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">
                        {new Date(member.created_at).toLocaleDateString('tr-TR')}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => removeMemberMutation.mutate(member.id)}
                          className="text-xs text-red-500 hover:text-red-700 transition-colors"
                        >
                          Kaldir
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

      {/* Edit Modal */}
      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title="Kampanyayi Düzenle">
        <div className="space-y-3">
          <Input
            label="Kampanya Adi"
            value={editForm.name ?? ''}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
          />
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Durum
            </label>
            <select
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              value={editForm.status ?? ''}
              onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
            >
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Açıklama
            </label>
            <textarea
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400 focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              rows={2}
              value={editForm.description ?? ''}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Baslangic Tarihi"
              type="date"
              value={editForm.start_date ?? ''}
              onChange={(e) => setEditForm({ ...editForm, start_date: e.target.value })}
            />
            <Input
              label="Bitis Tarihi"
              type="date"
              value={editForm.end_date ?? ''}
              onChange={(e) => setEditForm({ ...editForm, end_date: e.target.value })}
            />
          </div>
          <Input
            label="Butce"
            type="number"
            min={0}
            step={0.01}
            value={editForm.budget != null ? String(editForm.budget) : ''}
            onChange={(e) =>
              setEditForm({
                ...editForm,
                budget: e.target.value ? parseFloat(e.target.value) : undefined,
              })
            }
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setIsEditOpen(false)}>
            İptal
          </Button>
          <Button
            onClick={() => updateMutation.mutate(editForm as Record<string, unknown>)}
            loading={updateMutation.isPending}
          >
            Kaydet
          </Button>
        </div>
      </Modal>

      {/* Add Members Modal */}
      <Modal
        isOpen={isAddMembersOpen}
        onClose={() => {
          setIsAddMembersOpen(false);
          setMemberSearch('');
        }}
        title="Üye Ekle"
        size="sm"
      >
        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => setMemberType('customer')}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              memberType === 'customer'
                ? 'bg-honeywell-red text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Müşteri
          </button>
          <button
            type="button"
            onClick={() => setMemberType('lead')}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              memberType === 'lead'
                ? 'bg-honeywell-red text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Lead
          </button>
        </div>
        <Input
          label="Ara"
          placeholder={memberType === 'customer' ? 'Müşteri ara...' : 'Lead ara...'}
          value={memberSearch}
          onChange={(e) => setMemberSearch(e.target.value)}
        />
        <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
          {memberSearch.length < 2 && (
            <p className="px-4 py-3 text-sm text-gray-400">En az 2 karakter girin</p>
          )}
          {memberSearch.length >= 2 &&
            (!customerResults?.items || customerResults.items.length === 0) && (
              <p className="px-4 py-3 text-sm text-gray-400">Sonuç bulunamadi</p>
            )}
          {customerResults?.items?.map((item) => {
            const label =
              memberType === 'customer'
                ? `${(item as Customer).name} — ${(item as Customer).company || ''}`
                : `${(item as { first_name: string; last_name: string }).first_name} ${(item as { first_name: string; last_name: string }).last_name}`;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleAddMember(item)}
                className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <span className="font-medium text-gray-900 dark:text-white">{label}</span>
                <span className="ml-2 text-xs text-gray-400">{item.email}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            variant="secondary"
            onClick={() => {
              setIsAddMembersOpen(false);
              setMemberSearch('');
            }}
          >
            Kapat
          </Button>
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title="Kampanyayi Sil"
        size="sm"
      >
        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          <strong>{campaign.name}</strong> kampanyasini silmek istediginize emin misiniz? Bu işlem
          geri alinamaz.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setIsDeleteOpen(false)}>
            İptal
          </Button>
          <Button
            variant="danger"
            onClick={() => deleteMutation.mutate()}
            loading={deleteMutation.isPending}
          >
            Sil
          </Button>
        </div>
      </Modal>
    </div>
  );
}
