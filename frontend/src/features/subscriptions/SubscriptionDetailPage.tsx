import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, XCircle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { subscriptionsApi } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/formatters';
import type { Subscription } from '../../lib/types';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  paused: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  expired: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
};

const STATUS_KEYS: Record<string, TranslationKey> = {
  active: 'subscription.status_active',
  paused: 'subscription.status_paused',
  cancelled: 'subscription.status_cancelled',
  expired: 'subscription.status_expired',
};

const CYCLE_KEYS: Record<string, TranslationKey> = {
  monthly: 'subscription.cycle_monthly',
  quarterly: 'subscription.cycle_quarterly',
  annual: 'subscription.cycle_annual',
};

interface ParsedItem {
  spare_part_id?: number;
  quantity?: number;
  unit_price?: number;
  recurring_amount?: number;
  description?: string;
}

function parseItems(json: string | null): ParsedItem[] {
  if (!json) return [];
  try {
    return JSON.parse(json) as ParsedItem[];
  } catch {
    return [];
  }
}

export default function SubscriptionDetailPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const statusLabel = (s: string) => {
    const k = STATUS_KEYS[s];
    return k ? t(k) : s;
  };

  const cycleLabel = (c: string) => {
    const k = CYCLE_KEYS[c];
    return k ? t(k) : c;
  };

  const { data: sub, isLoading } = useQuery<Subscription>({
    queryKey: ['subscriptions', id],
    queryFn: () => subscriptionsApi.get(Number(id)),
    enabled: !!id,
  });

  const cancelMutation = useMutation({
    mutationFn: () => subscriptionsApi.cancel(Number(id)),
    onSuccess: () => {
      toast.success(t('subscription.toast_cancelled'));
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
    onError: () => toast.error(t('subscription.toast_cancel_fail')),
  });

  const renewMutation = useMutation({
    mutationFn: () => subscriptionsApi.renew(Number(id)),
    onSuccess: () => {
      toast.success(t('subscription.toast_renewed'));
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
    onError: () => toast.error(t('subscription.toast_renew_fail')),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-slate-400">{t('subscription.loading')}</p>
      </div>
    );
  }

  if (!sub) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-slate-400">{t('subscription.not_found')}</p>
      </div>
    );
  }

  const items = parseItems(sub.items_json);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate('/subscriptions')}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors cursor-pointer"
        >
          <ArrowLeft size={16} />
          {t('subscription.back_list')}
        </button>
        <div className="flex gap-2">
          {sub.status === 'active' && (
            <>
              <button
                type="button"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
                className="flex items-center gap-2 rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors cursor-pointer"
              >
                <XCircle size={16} />
                {t('subscription.cancel')}
              </button>
              <button
                type="button"
                onClick={() => renewMutation.mutate()}
                disabled={renewMutation.isPending}
                className="flex items-center gap-2 rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors cursor-pointer"
              >
                <RefreshCw size={16} />
                {t('subscription.renew')}
              </button>
            </>
          )}
          {sub.status === 'cancelled' && (
            <button
              type="button"
              onClick={() => renewMutation.mutate()}
              disabled={renewMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors cursor-pointer"
            >
              <RefreshCw size={16} />
              {t('subscription.restart')}
            </button>
          )}
        </div>
      </div>

      <div
        className="rounded-xl border p-6"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
      >
        <div className="mb-4 flex items-center gap-3">
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
            {sub.name}
          </h1>
          <span
            className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[sub.status] ?? ''}`}
          >
            {statusLabel(sub.status)}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_billing_period')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {cycleLabel(sub.billing_cycle)}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_mrr_short')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {formatCurrency(sub.mrr, sub.currency)}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_start_date')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.start_date}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_end_date')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.end_date ?? '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_next_renewal')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.next_renewal_date ?? '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_auto_renew_long')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.auto_renew ? t('subscription.yes') : t('subscription.no')}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_currency_short')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.currency}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">{t('subscription.lbl_created')}</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.created_at ? formatDate(sub.created_at) : '-'}
            </p>
          </div>
        </div>
      </div>

      {items.length > 0 && (
        <div
          className="rounded-xl border p-6"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
        >
          <h2 className="mb-4 text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
            {t('subscription.items_title')}
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left" style={{ borderColor: 'var(--border)' }}>
                  <th className="px-4 py-2 font-medium text-slate-500">
                    {t('subscription.lbl_description')}
                  </th>
                  <th className="px-4 py-2 font-medium text-slate-500">
                    {t('subscription.col_qty')}
                  </th>
                  <th className="px-4 py-2 font-medium text-slate-500">
                    {t('subscription.col_unit_price')}
                  </th>
                  <th className="px-4 py-2 font-medium text-slate-500">
                    {t('subscription.col_recurring')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <tr key={idx} className="border-b" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-2" style={{ color: 'var(--text-primary)' }}>
                      {item.description ??
                        t('subscription.line_part').replace(
                          '{id}',
                          String(item.spare_part_id ?? idx + 1),
                        )}
                    </td>
                    <td className="px-4 py-2 text-slate-500">{item.quantity ?? '-'}</td>
                    <td className="px-4 py-2 text-slate-500">
                      {item.unit_price != null
                        ? formatCurrency(item.unit_price, sub.currency)
                        : '-'}
                    </td>
                    <td className="px-4 py-2 font-medium" style={{ color: 'var(--text-primary)' }}>
                      {item.recurring_amount != null
                        ? formatCurrency(item.recurring_amount, sub.currency)
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
