import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Modal } from '../../components/ui/Modal';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { bundlesApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { ProductBundle } from '../../lib/types';
import { useT } from '../../hooks/useT';

interface BundleQuoteItem {
  spare_part_id: number;
  honeywell_code: string;
  description: string;
  quantity: number;
  unit_price: number;
  discount_pct: number;
}

interface BundleSelectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddItems: (items: BundleQuoteItem[]) => void;
}

export default function BundleSelectorModal({
  isOpen,
  onClose,
  onAddItems,
}: BundleSelectorModalProps) {
  const t = useT();
  const { data, isLoading } = useQuery<{ bundles: ProductBundle[] }>({
    queryKey: ['bundles'],
    queryFn: () => bundlesApi.list(),
    enabled: isOpen,
  });

  const expandMutation = useMutation({
    mutationFn: (bundleId: number) => bundlesApi.toQuoteItems(bundleId),
    onSuccess: (result: { items: BundleQuoteItem[]; bundle_name: string }) => {
      if (result.items.length === 0) {
        toast.error(t('quotes.bundle_no_items'));
        return;
      }
      onAddItems(result.items);
      toast.success(t('quotes.bundle_added').replace('{name}', result.bundle_name));
      onClose();
    },
    onError: () => toast.error(t('quotes.bundle_expand_fail')),
  });

  const bundles = data?.bundles ?? [];

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('quotes.bundle_title')}>
      <div className="space-y-4">
        {isLoading ? (
          <Skeleton variant="card" count={3} />
        ) : bundles.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">{t('quotes.bundle_empty')}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {bundles.map((bundle) => (
              <Card key={bundle.id}>
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-slate-900">{bundle.name}</h4>
                  {bundle.description && (
                    <p className="text-xs text-slate-500">{bundle.description}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info" size="sm">
                      {t('quotes.bundle_item_count').replace(
                        '{count}',
                        String(bundle.items.length),
                      )}
                    </Badge>
                    {bundle.bundle_price != null && (
                      <Badge variant="success" size="sm">
                        {t('quotes.bundle_price_prefix')}{' '}
                        {formatCurrency(bundle.bundle_price, 'TRY')}
                      </Badge>
                    )}
                    {bundle.discount_pct > 0 && (
                      <Badge variant="warning" size="sm">
                        {t('quotes.bundle_discount_prefix')} %{bundle.discount_pct}
                      </Badge>
                    )}
                  </div>
                  <div className="pt-1">
                    <Button
                      size="sm"
                      loading={expandMutation.isPending}
                      onClick={() => expandMutation.mutate(bundle.id)}
                    >
                      {t('quotes.bundle_add')}
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
