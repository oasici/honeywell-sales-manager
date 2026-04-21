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
import { formatCurrency, formatDate, currentLocale } from '../../lib/formatters';
import { Modal } from '../../components/ui/Modal';
import type { Campaign, CampaignMember, CampaignROI, Customer } from '../../lib/types';
import { Pencil, Trash2, UserPlus } from 'lucide-react';
import { STATUS_VARIANTS } from './campaignConstants';
import { useT } from '../../hooks/useT';
import {
  CAMPAIGN_MEMBER_STATUS_VALUES,
  CAMPAIGN_STATUS_VALUES,
  translateCampaignMemberStatus,
  translateCampaignStatus,
  translateCampaignType,
} from '../../lib/labelTranslations';

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
  const t = useT();
  const locale = currentLocale();
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
      toast.success(t('campaigns.toast_updated'));
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId] });
      setIsEditOpen(false);
    },
    onError: () => toast.error(t('campaigns.toast_update_failed')),
  });

  const deleteMutation = useMutation({
    mutationFn: () => campaignsApi.delete(campaignId),
    onSuccess: () => {
      toast.success(t('campaigns.toast_deleted'));
      navigate('/campaigns');
    },
    onError: () => toast.error(t('campaigns.toast_delete_failed')),
  });

  const addMembersMutation = useMutation({
    mutationFn: (members: Array<{ lead_id?: number; customer_id?: number }>) =>
      campaignsApi.addMembers(campaignId, members),
    onSuccess: () => {
      toast.success(t('campaigns.toast_member_added'));
      queryClient.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId] });
      setIsAddMembersOpen(false);
      setMemberSearch('');
    },
    onError: () => toast.error(t('campaigns.toast_member_add_failed')),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: number) => campaignsApi.removeMember(campaignId, memberId),
    onSuccess: () => {
      toast.success(t('campaigns.toast_member_removed'));
      queryClient.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
    },
    onError: () => toast.error(t('campaigns.toast_member_remove_failed')),
  });

  const updateMemberStatusMutation = useMutation({
    mutationFn: ({ memberId, status }: { memberId: number; status: string }) =>
      campaignsApi.updateMemberStatus(campaignId, memberId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaign-members', campaignId] });
    },
    onError: () => toast.error(t('campaigns.toast_member_status_failed')),
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
        <p className="text-sm text-gray-500">{t('campaigns.detail_not_found')}</p>
        <Button variant="secondary" onClick={() => navigate('/campaigns')} className="mt-4">
          {t('common.back')}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={campaign.name} description={t('campaigns.detail_description')}>
        <Badge variant={STATUS_VARIANTS[campaign.status] || 'default'}>
          {translateCampaignStatus(campaign.status, t)}
        </Badge>
        <Button variant="secondary" onClick={() => navigate('/campaigns')}>
          {t('common.back')}
        </Button>
        <Button variant="secondary" onClick={handleOpenEdit}>
          <Pencil className="mr-1.5 h-4 w-4" />
          {t('campaigns.edit')}
        </Button>
        <Button
          variant="danger"
          onClick={() => setIsDeleteOpen(true)}
          loading={deleteMutation.isPending}
        >
          <Trash2 className="mr-1.5 h-4 w-4" />
          {t('campaigns.delete')}
        </Button>
      </PageHeader>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <KpiCard
          label={t('campaigns.kpi_actual_cost')}
          value={formatCurrency(roi?.actual_cost ?? campaign.actual_cost)}
        />
        <KpiCard
          label={t('campaigns.kpi_actual_revenue')}
          value={formatCurrency(roi?.actual_revenue ?? campaign.actual_revenue)}
        />
        <KpiCard
          label={t('campaigns.kpi_roi')}
          value={roi ? `${roi.roi_pct.toFixed(1)}%` : '-'}
          sub={
            roi
              ? t('campaigns.kpi_roi_sub').replace('{count}', String(roi.member_count))
              : undefined
          }
        />
        <KpiCard
          label={t('campaigns.kpi_conversion')}
          value={roi ? `${roi.conversion_rate.toFixed(1)}%` : '-'}
          sub={
            roi
              ? t('campaigns.kpi_conversion_sub').replace('{count}', String(roi.responded_count))
              : undefined
          }
        />
      </div>

      {/* Campaign Info */}
      <Card title={t('campaigns.card_info')}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-xs text-gray-500">{t('campaigns.field_type')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {translateCampaignType(campaign.type, t)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('campaigns.field_status')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {translateCampaignStatus(campaign.status, t)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('campaigns.field_start')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {campaign.start_date ? formatDate(campaign.start_date, locale) : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('campaigns.field_end')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {campaign.end_date ? formatDate(campaign.end_date, locale) : '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('campaigns.field_budget')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {formatCurrency(campaign.budget)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t('campaigns.field_expected_revenue')}</p>
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {formatCurrency(campaign.expected_revenue)}
            </p>
          </div>
          {campaign.description && (
            <div className="col-span-full">
              <p className="text-xs text-gray-500">{t('campaigns.field_description')}</p>
              <p className="text-sm text-gray-700 dark:text-gray-300">{campaign.description}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Members Section */}
      <Card title={t('campaigns.members_title').replace('{count}', String(members.length))}>
        <div className="mb-3 flex justify-end">
          <Button onClick={() => setIsAddMembersOpen(true)}>
            <UserPlus className="mr-1.5 h-4 w-4" />
            {t('campaigns.add_member')}
          </Button>
        </div>

        {membersLoading && <Skeleton variant="table" count={3} />}

        {!membersLoading && members.length === 0 && (
          <p className="py-6 text-center text-sm text-gray-400">{t('campaigns.members_empty')}</p>
        )}

        {!membersLoading && members.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('campaigns.col_name_company')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('campaigns.col_type')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('campaigns.col_email')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('campaigns.col_status')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('campaigns.col_added')}
                  </th>
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
                          {isLead ? t('campaigns.badge_lead') : t('campaigns.badge_customer')}
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
                          {CAMPAIGN_MEMBER_STATUS_VALUES.map((v) => (
                            <option key={v} value={v}>
                              {translateCampaignMemberStatus(v, t)}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">
                        {formatDate(member.created_at, locale)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => removeMemberMutation.mutate(member.id)}
                          className="text-xs text-red-500 hover:text-red-700 transition-colors"
                        >
                          {t('campaigns.remove_member')}
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
      <Modal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        title={t('campaigns.modal_edit_title')}
      >
        <div className="space-y-3">
          <Input
            label={t('campaigns.label_name')}
            value={editForm.name ?? ''}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
          />
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('campaigns.field_status')}
            </label>
            <select
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              value={editForm.status ?? ''}
              onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
            >
              {CAMPAIGN_STATUS_VALUES.map((k) => (
                <option key={k} value={k}>
                  {translateCampaignStatus(k, t)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('campaigns.field_description')}
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
              label={t('campaigns.label_start_date')}
              type="date"
              value={editForm.start_date ?? ''}
              onChange={(e) => setEditForm({ ...editForm, start_date: e.target.value })}
            />
            <Input
              label={t('campaigns.label_end_date')}
              type="date"
              value={editForm.end_date ?? ''}
              onChange={(e) => setEditForm({ ...editForm, end_date: e.target.value })}
            />
          </div>
          <Input
            label={t('campaigns.label_budget')}
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
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => updateMutation.mutate(editForm as Record<string, unknown>)}
            loading={updateMutation.isPending}
          >
            {t('common.save')}
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
        title={t('campaigns.modal_add_member_title')}
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
            {t('campaigns.badge_customer')}
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
            {t('campaigns.badge_lead')}
          </button>
        </div>
        <Input
          label={t('campaigns.search')}
          placeholder={
            memberType === 'customer'
              ? t('campaigns.search_customer_ph')
              : t('campaigns.search_lead_ph')
          }
          value={memberSearch}
          onChange={(e) => setMemberSearch(e.target.value)}
        />
        <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
          {memberSearch.length < 2 && (
            <p className="px-4 py-3 text-sm text-gray-400">{t('campaigns.search_min_chars')}</p>
          )}
          {memberSearch.length >= 2 &&
            (!customerResults?.items || customerResults.items.length === 0) && (
              <p className="px-4 py-3 text-sm text-gray-400">{t('campaigns.no_results')}</p>
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
            {t('campaigns.close')}
          </Button>
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title={t('campaigns.delete_title')}
        size="sm"
      >
        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          {t('campaigns.delete_confirm').replace('{name}', campaign.name)}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setIsDeleteOpen(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="danger"
            onClick={() => deleteMutation.mutate()}
            loading={deleteMutation.isPending}
          >
            {t('campaigns.delete')}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
