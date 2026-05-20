import { useState, useCallback, useMemo, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { onContractChanged } from '../../lib/cacheInvalidation';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { contractsApi } from '../../lib/api';
import type { Contract, ContractAmendment } from '../../lib/types';
import { useT } from '../../hooks/useT';
import {
  CONTRACT_AMENDMENT_VALUES,
  translateContractAmendmentType,
  translateContractStatus,
} from '../../lib/labelTranslations';
import { formatDate, currentLocale } from '../../lib/formatters';

const STATUS_BADGES: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-700',
  active: 'bg-green-100 text-green-700',
  amended: 'bg-yellow-100 text-yellow-700',
  expired: 'bg-red-100 text-red-700',
  terminated: 'bg-red-200 text-red-800',
};

const STATUS_FLOW = ['draft', 'active', 'amended', 'expired'];

export default function ContractDetailPage() {
  const t = useT();
  const locale = currentLocale();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const contractId = Number(id);

  const [isAmendOpen, setIsAmendOpen] = useState(false);
  const [amendType, setAmendType] = useState('modification');
  const [amendChanges, setAmendChanges] = useState('');
  const [amendDate, setAmendDate] = useState('');

  const { data: contract, isLoading } = useQuery<Contract>({
    queryKey: ['contract', contractId],
    queryFn: () => contractsApi.get(contractId),
    enabled: !!contractId,
  });

  const activateMutation = useMutation({
    mutationFn: () => contractsApi.activate(contractId),
    onSuccess: () => {
      toast.success(t('contracts.toast_activated'));
      // R4-CACHE-5 — list page also needs to refresh, not just detail.
      onContractChanged(queryClient, contractId);
    },
    onError: () => toast.error(t('contracts.toast_activate_failed')),
  });

  // R7-FORM-3 — inline edit. Pre-fix the SPA only had "activate" and
  // "amend" affordances, so a typo in title or value forced an
  // audit-tracked amendment workflow.
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    title: '',
    value: '',
    start_date: '',
    end_date: '',
    terms_json: '',
  });

  useEffect(() => {
    if (contract) {
      setEditForm({
        title: contract.title || '',
        value: contract.value != null ? String(contract.value) : '',
        start_date: contract.start_date || '',
        end_date: contract.end_date || '',
        terms_json: contract.terms_json || '',
      });
    }
  }, [contract]);

  const updateMutation = useMutation({
    mutationFn: (payload: typeof editForm) => {
      let termsJsonNormalized: unknown = undefined;
      if (payload.terms_json.trim()) {
        try {
          termsJsonNormalized = JSON.parse(payload.terms_json);
        } catch {
          // Re-throw as a friendly toast, not as a JSON exception.
          throw new Error(t('contracts.err_terms_invalid_json'));
        }
      }
      const wire: Record<string, unknown> = {
        title: payload.title.trim() || undefined,
      };
      if (payload.value.trim() !== '') wire.value = parseFloat(payload.value);
      if (payload.start_date) wire.start_date = payload.start_date;
      if (payload.end_date) wire.end_date = payload.end_date;
      if (termsJsonNormalized !== undefined) wire.terms_json = JSON.stringify(termsJsonNormalized);
      return contractsApi.update(contractId, wire);
    },
    onSuccess: () => {
      toast.success(t('contracts.toast_updated'));
      setEditing(false);
      onContractChanged(queryClient, contractId);
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : t('contracts.toast_update_failed');
      toast.error(msg);
    },
  });

  const amendMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => contractsApi.amend(contractId, payload),
    onSuccess: () => {
      toast.success(t('contracts.toast_amend_added'));
      onContractChanged(queryClient, contractId);
      setIsAmendOpen(false);
      setAmendType('modification');
      setAmendChanges('');
      setAmendDate('');
    },
    onError: () => toast.error(t('contracts.toast_amend_failed')),
  });

  const handleAmend = useCallback(() => {
    amendMutation.mutate({
      amendment_type: amendType,
      changes_json: amendChanges || undefined,
      effective_date: amendDate || undefined,
    });
  }, [amendType, amendChanges, amendDate, amendMutation]);

  const amendmentTypeOptions = useMemo(
    () =>
      CONTRACT_AMENDMENT_VALUES.map((value) => ({
        value,
        label: translateContractAmendmentType(value, t),
      })),
    [t],
  );

  if (isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!contract) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-slate-500">{t('contracts.detail_not_found')}</p>
        <Button variant="secondary" onClick={() => navigate('/contracts')} className="mt-4">
          {t('common.back')}
        </Button>
      </div>
    );
  }

  const amendments: ContractAmendment[] = contract.amendments || [];

  return (
    <div>
      <PageHeader title={contract.title} description={t('contracts.detail_description')}>
        <span
          className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${STATUS_BADGES[contract.status] || 'bg-slate-100 text-slate-700'}`}
        >
          {translateContractStatus(contract.status, t)}
        </span>
        <Button variant="secondary" onClick={() => navigate('/contracts')}>
          {t('common.back')}
        </Button>
        {contract.status === 'draft' && (
          <Button
            onClick={() => activateMutation.mutate()}
            loading={activateMutation.isPending}
            className="bg-green-600! text-white! hover:bg-green-700!"
          >
            {t('contracts.activate')}
          </Button>
        )}
        {/* R7-FORM-3 — Düzenle. Pre-fix only Amend was available. */}
        {!editing && (
          <Button variant="secondary" onClick={() => setEditing(true)}>
            {t('common.edit')}
          </Button>
        )}
        <Button variant="secondary" onClick={() => setIsAmendOpen(true)}>
          {t('contracts.add_amendment')}
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* R7-FORM-3 — inline edit panel. */}
        {editing && (
          <Card title={t('contracts.edit_panel_title')}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Input
                  label={t('contracts.field_title')}
                  value={editForm.title}
                  onChange={(e) => setEditForm((p) => ({ ...p, title: e.target.value }))}
                />
              </div>
              <Input
                label={t('contracts.field_amount')}
                type="number"
                min={0}
                step="0.01"
                value={editForm.value}
                onChange={(e) => setEditForm((p) => ({ ...p, value: e.target.value }))}
              />
              <div className="grid grid-cols-2 gap-3 sm:col-span-2">
                <Input
                  label={t('contracts.field_start_date')}
                  type="date"
                  value={editForm.start_date}
                  onChange={(e) => setEditForm((p) => ({ ...p, start_date: e.target.value }))}
                />
                <Input
                  label={t('contracts.field_end_date')}
                  type="date"
                  value={editForm.end_date}
                  onChange={(e) => setEditForm((p) => ({ ...p, end_date: e.target.value }))}
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
                  {t('contracts.field_terms_json')}
                </label>
                <textarea
                  rows={4}
                  value={editForm.terms_json}
                  onChange={(e) => setEditForm((p) => ({ ...p, terms_json: e.target.value }))}
                  className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
                  style={{
                    borderColor: 'var(--border)',
                    backgroundColor: 'var(--surface)',
                    color: 'var(--text-primary)',
                  }}
                  placeholder={'{"sla":"99.9","payment_terms":"net30"}'}
                />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditing(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                onClick={() => updateMutation.mutate(editForm)}
                loading={updateMutation.isPending}
              >
                {t('common.save')}
              </Button>
            </div>
          </Card>
        )}

        {/* Status Flow */}
        <Card title={t('contracts.card_status_flow')}>
          <div className="flex items-center gap-1">
            {STATUS_FLOW.map((step, idx) => {
              const isCurrent = contract.status === step;
              const isPast = STATUS_FLOW.indexOf(contract.status) > idx;
              return (
                <div key={step} className="flex items-center gap-1">
                  {idx > 0 && (
                    <div className={`h-0.5 w-8 ${isPast ? 'bg-green-400' : 'bg-gray-200'}`} />
                  )}
                  <div
                    className={`flex items-center justify-center rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      isCurrent
                        ? 'bg-honeywell-red text-white'
                        : isPast
                          ? 'bg-green-100 text-green-700'
                          : 'bg-slate-100 text-slate-400'
                    }`}
                  >
                    {translateContractStatus(step, t)}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Contract Info */}
        <Card title={t('contracts.card_info')}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-slate-500">{t('contracts.field_customer_id')}</p>
              {/* Round-15 §8.1 quick-win — backend embeds a customer
                  summary (id, name, company) on the contract response.
                  Pre-fix this cell showed the bare id (e.g. ``#293``);
                  now it shows the company / name with a soft fallback to
                  the id when the summary is absent. */}
              <p className="text-sm font-medium text-slate-900">
                {contract.customer
                  ? `${contract.customer.company || contract.customer.name}`
                  : `#${contract.customer_id}`}
              </p>
              {contract.customer?.name && contract.customer.company && (
                <p className="text-xs text-slate-500">{contract.customer.name}</p>
              )}
            </div>
            {contract.quote_id && (
              <div>
                <p className="text-xs text-slate-500">{t('contracts.field_quote_id')}</p>
                <p className="text-sm font-medium text-slate-900">{contract.quote_id}</p>
              </div>
            )}
            <div>
              <p className="text-xs text-slate-500">{t('contracts.field_start')}</p>
              <p className="text-sm font-medium text-slate-900">
                {contract.start_date ? formatDate(contract.start_date, locale) : '-'}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">{t('contracts.field_end')}</p>
              <p className="text-sm font-medium text-slate-900">
                {contract.end_date ? formatDate(contract.end_date, locale) : '-'}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">{t('contracts.field_value')}</p>
              <p className="text-sm font-medium text-slate-900">
                {contract.value != null
                  ? contract.value.toLocaleString(locale, { minimumFractionDigits: 2 })
                  : '-'}
              </p>
            </div>
            {contract.signed_at && (
              <div>
                <p className="text-xs text-slate-500">{t('contracts.field_signed')}</p>
                <p className="text-sm font-medium text-slate-900">
                  {formatDate(contract.signed_at, locale)}
                  {contract.signed_by && (
                    <span className="text-slate-500"> - {contract.signed_by}</span>
                  )}
                </p>
              </div>
            )}
            {/* Created-by attribution — fetched but never rendered
                pre-audit F-18. */}
            {contract.created_by != null && (
              <div>
                <p className="text-xs text-slate-500">{t('contracts.field_created_by')}</p>
                <p className="text-sm font-medium text-slate-900">#{contract.created_by}</p>
              </div>
            )}
          </div>
        </Card>

        {/* Contract terms — usually the entire substantive content
            of the contract. Backend serializes terms_json to a string
            blob; pretty-print it best-effort with a JSON fallback. */}
        {contract.terms_json && (
          <Card title={t('contracts.card_terms')}>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700 dark:bg-slate-900 dark:text-slate-300">
              {(() => {
                try {
                  return JSON.stringify(JSON.parse(contract.terms_json), null, 2);
                } catch {
                  return contract.terms_json;
                }
              })()}
            </pre>
          </Card>
        )}

        {/* Amendment Timeline */}
        <Card title={t('contracts.amendments_title')}>
          {amendments.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('contracts.amendments_empty')}
            </p>
          ) : (
            <div className="relative pl-6">
              <div className="absolute left-2 top-0 bottom-0 w-0.5 bg-gray-200" />
              <div className="space-y-4">
                {amendments.map((amendment) => (
                  <div key={amendment.id} className="relative">
                    <div className="absolute -left-4 top-1.5 h-3 w-3 rounded-full border-2 border-honeywell-red bg-white" />
                    <div className="rounded-lg border border-slate-100 bg-slate-50 p-3 ml-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-700">
                          {translateContractAmendmentType(amendment.amendment_type, t)}
                        </span>
                        {amendment.effective_date && (
                          <span className="text-xs text-slate-400">
                            {t('contracts.amendment_effective').replace(
                              '{date}',
                              amendment.effective_date,
                            )}
                          </span>
                        )}
                      </div>
                      {amendment.changes_json && (
                        <p className="mt-1 text-xs text-slate-600">{amendment.changes_json}</p>
                      )}
                      <p className="mt-1 text-[10px] text-slate-400">
                        {amendment.created_at ? formatDate(amendment.created_at, locale) : ''}
                        {/* Round-15 §8.1 quick-win — surface
                            ``amendment.approved_by`` which the backend
                            has emitted since R6 but the timeline never
                            rendered. Useful for audit trails when an
                            amendment is challenged. */}
                        {amendment.approved_by != null && (
                          <span className="ml-2">· #{amendment.approved_by}</span>
                        )}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Amendment Modal */}
      {isAmendOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-slate-900">
              {t('contracts.modal_amend_title')}
            </h3>
            <div className="space-y-3">
              <Select
                label={t('contracts.label_amendment_type')}
                options={amendmentTypeOptions}
                value={amendType}
                onChange={(e) => setAmendType(e.target.value)}
              />
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  {t('contracts.field_description')}
                </label>
                <textarea
                  className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-honeywell-light focus:border-honeywell-red"
                  rows={3}
                  value={amendChanges}
                  onChange={(e) => setAmendChanges(e.target.value)}
                  placeholder={t('contracts.amendment_changes_ph')}
                />
              </div>
              <Input
                label={t('contracts.label_effective_date')}
                type="date"
                value={amendDate}
                onChange={(e) => setAmendDate(e.target.value)}
              />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setIsAmendOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleAmend} loading={amendMutation.isPending}>
                {t('contracts.add')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
