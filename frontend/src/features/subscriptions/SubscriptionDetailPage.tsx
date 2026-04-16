import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, XCircle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { subscriptionsApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { Subscription } from '../../lib/types';

const STATUS_LABELS: Record<string, string> = {
  active: 'Aktif',
  paused: 'Duraklatildi',
  cancelled: 'Iptal Edildi',
  expired: 'Suresi Doldu',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  paused: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  expired: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const CYCLE_LABELS: Record<string, string> = {
  monthly: 'Aylik',
  quarterly: 'Ceyrektik',
  annual: 'Yillik',
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
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: sub, isLoading } = useQuery<Subscription>({
    queryKey: ['subscriptions', id],
    queryFn: () => subscriptionsApi.get(Number(id)),
    enabled: !!id,
  });

  const cancelMutation = useMutation({
    mutationFn: () => subscriptionsApi.cancel(Number(id)),
    onSuccess: () => {
      toast.success('Abonelik iptal edildi');
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
    onError: () => toast.error('Iptal islemi basarisiz'),
  });

  const renewMutation = useMutation({
    mutationFn: () => subscriptionsApi.renew(Number(id)),
    onSuccess: () => {
      toast.success('Abonelik yenilendi');
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] });
    },
    onError: () => toast.error('Yenileme islemi basarisiz'),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-gray-400">Yukleniyor...</p>
      </div>
    );
  }

  if (!sub) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-gray-400">Abonelik bulunamadi</p>
      </div>
    );
  }

  const items = parseItems(sub.items_json);

  return (
    <div className="space-y-6">
      {/* Back button + actions */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate('/subscriptions')}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors cursor-pointer"
        >
          <ArrowLeft size={16} />
          Aboneliklere Don
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
                Iptal Et
              </button>
              <button
                type="button"
                onClick={() => renewMutation.mutate()}
                disabled={renewMutation.isPending}
                className="flex items-center gap-2 rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors cursor-pointer"
              >
                <RefreshCw size={16} />
                Yenile
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
              Yeniden Baslat
            </button>
          )}
        </div>
      </div>

      {/* Info card */}
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
            {STATUS_LABELS[sub.status] ?? sub.status}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-gray-500">Fatura Donemi</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {CYCLE_LABELS[sub.billing_cycle] ?? sub.billing_cycle}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Aylik Gelir (MRR)</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {formatCurrency(sub.mrr, sub.currency)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Baslangic Tarihi</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.start_date}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Bitis Tarihi</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.end_date ?? '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Sonraki Yenileme</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.next_renewal_date ?? '-'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Otomatik Yenileme</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.auto_renew ? 'Evet' : 'Hayir'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Para Birimi</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.currency}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Olusturulma</p>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {sub.created_at ? new Date(sub.created_at).toLocaleDateString('tr-TR') : '-'}
            </p>
          </div>
        </div>
      </div>

      {/* Items */}
      {items.length > 0 && (
        <div
          className="rounded-xl border p-6"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface)' }}
        >
          <h2 className="mb-4 text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
            Abonelik Kalemleri
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left" style={{ borderColor: 'var(--border)' }}>
                  <th className="px-4 py-2 font-medium text-gray-500">Aciklama</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Adet</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Birim Fiyat</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Tekrar Eden Tutar</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <tr key={idx} className="border-b" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-2" style={{ color: 'var(--text-primary)' }}>
                      {item.description ?? `Parca #${item.spare_part_id ?? idx + 1}`}
                    </td>
                    <td className="px-4 py-2 text-gray-500">{item.quantity ?? '-'}</td>
                    <td className="px-4 py-2 text-gray-500">
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
