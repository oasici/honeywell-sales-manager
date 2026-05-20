import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Pin, PinOff, Target } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { customersApi } from '../../lib/api';
import { onCustomerChanged } from '../../lib/cacheInvalidation';
import { useT } from '../../hooks/useT';
import type { HighIntentListResponse } from '../../lib/types';

export default function HighIntentAccountsPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery<HighIntentListResponse>({
    queryKey: ['high-intent-accounts'],
    queryFn: () => customersApi.listHighIntent({ limit: 100 }) as Promise<HighIntentListResponse>,
  });

  const pinMutation = useMutation({
    mutationFn: async ({ id, pin }: { id: number; pin: boolean }) => {
      if (pin) await customersApi.pinCustomer(id);
      else await customersApi.unpinCustomer(id);
    },
    onSuccess: (_, v) => {
      onCustomerChanged(queryClient, v.id);
      toast.success(v.pin ? t('high_intent.pinned') : t('high_intent.unpinned'));
    },
    onError: () => toast.error(t('high_intent.pin_error')),
  });

  return (
    <div>
      <PageHeader title={t('high_intent.title')} description={t('high_intent.subtitle')}>
        <Button variant="secondary" onClick={() => navigate('/customers')}>
          {t('high_intent.back_customers')}
        </Button>
      </PageHeader>

      <Card title={t('high_intent.list_title')}>
        {isError ? (
          <QueryErrorBanner variant="block" onRetry={() => refetch()} />
        ) : isLoading ? (
          <Skeleton variant="card" />
        ) : !data?.items?.length ? (
          <div className="flex flex-col items-center justify-center py-12 text-center text-slate-500">
            <Target className="mb-2 h-10 w-10 opacity-40" />
            <p className="text-sm">{t('high_intent.empty')}</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-200 dark:divide-slate-800">
            {data.items.map((row) => (
              <div
                key={row.customer_id}
                className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => navigate(`/customers/${row.customer_id}`)}
                    className="text-left font-semibold text-honeywell-red hover:underline"
                  >
                    {row.company || row.name}
                  </button>
                  {row.company && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                      {row.name}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {row.signals.map((s) => (
                      <Badge key={s} variant="default" size="sm">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <p className="text-xs text-slate-500">{t('high_intent.score')}</p>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">{row.score}</p>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={pinMutation.isPending}
                    onClick={() => pinMutation.mutate({ id: row.customer_id, pin: !row.pinned })}
                  >
                    {row.pinned ? (
                      <>
                        <PinOff size={14} className="mr-1" />
                        {t('high_intent.unpin')}
                      </>
                    ) : (
                      <>
                        <Pin size={14} className="mr-1" />
                        {t('high_intent.pin')}
                      </>
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
