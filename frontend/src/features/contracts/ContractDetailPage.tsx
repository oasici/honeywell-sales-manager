import { useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
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
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
    },
    onError: () => toast.error(t('contracts.toast_activate_failed')),
  });

  const amendMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => contractsApi.amend(contractId, payload),
    onSuccess: () => {
      toast.success(t('contracts.toast_amend_added'));
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
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
            className="!bg-green-600 !text-white hover:!bg-green-700"
          >
            {t('contracts.activate')}
          </Button>
        )}
        <Button variant="secondary" onClick={() => setIsAmendOpen(true)}>
          {t('contracts.add_amendment')}
        </Button>
      </PageHeader>

      <div className="space-y-6">
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
              <p className="text-sm font-medium text-slate-900">{contract.customer_id}</p>
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
