import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { onRecordsMerged } from '../../lib/cacheInvalidation';
import { toast } from 'sonner';
import { CheckCircle2, XCircle, ArrowLeft } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { duplicatesApi } from '../../lib/api';
import { useState } from 'react';

interface RecordFields {
  [key: string]: unknown;
  id: number;
  name: string;
  company: string;
  email: string;
  phone: string;
  address: string;
  tax_id: string;
  preferred_lang: string;
  created_at: string | null;
}

interface MergePreviewData {
  winner: RecordFields;
  loser: RecordFields;
  related_counts: Record<string, number>;
}

const FIELD_LABELS: Record<string, string> = {
  id: 'ID',
  name: 'İsim',
  company: 'Şirket',
  email: 'Email',
  phone: 'Telefon',
  address: 'Adres',
  tax_id: 'Vergi No',
  preferred_lang: 'Tercih Edilen Dil',
  created_at: 'Oluşturma Tarihi',
};

const RELATED_LABELS: Record<string, string> = {
  quotes: 'Teklif',
  opportunities: 'Fırsat',
  emails: 'Email',
  activities: 'Aktivite',
  team_members: 'Takım Üyesi',
};

const DISPLAY_FIELDS: string[] = [
  'name',
  'company',
  'email',
  'phone',
  'address',
  'tax_id',
  'preferred_lang',
  'created_at',
];

interface RecordCardProps {
  title: string;
  record: RecordFields;
  variant: 'winner' | 'loser';
  highlightDifferentFrom?: RecordFields;
}

/**
 * RecordCard — side-by-side comparison panel for the merge preview.
 *
 * Visual:
 *   - Winner gets a brand-emerald accent strip + CheckCircle medallion.
 *   - Loser gets a red accent strip + XCircle medallion. Diff fields are
 *     highlighted with a subtle red tint so the user can see exactly what
 *     will be lost without scanning every row character-by-character.
 */
function RecordCard({ title, record, variant, highlightDifferentFrom }: RecordCardProps) {
  const isWinner = variant === 'winner';
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div
        className={[
          'flex items-center gap-2.5 border-b px-5 py-3.5',
          isWinner
            ? 'border-emerald-100 bg-emerald-50/40 dark:border-emerald-900/40 dark:bg-emerald-950/20'
            : 'border-red-100 bg-red-50/40 dark:border-red-900/40 dark:bg-red-950/20',
        ].join(' ')}
      >
        <span
          className={[
            'inline-flex h-8 w-8 items-center justify-center rounded-[10px] ring-1 ring-inset',
            isWinner
              ? 'bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-300 dark:ring-emerald-900/60'
              : 'bg-red-100 text-red-700 ring-red-200 dark:bg-red-900/40 dark:text-red-300 dark:ring-red-900/60',
          ].join(' ')}
        >
          {isWinner ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
        </span>
        <div className="min-w-0 flex-1">
          <h3
            className={[
              'text-[13px] font-semibold',
              isWinner
                ? 'text-emerald-800 dark:text-emerald-200'
                : 'text-red-800 dark:text-red-200',
            ].join(' ')}
          >
            {title}
          </h3>
          <p
            className={[
              'text-[11px]',
              isWinner
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-red-600 dark:text-red-400',
            ].join(' ')}
          >
            {isWinner ? 'Bu kayıt korunacak' : 'Bu kayıt silinecek'}
          </p>
        </div>
      </div>
      <dl className="divide-y divide-slate-100 dark:divide-slate-800">
        {DISPLAY_FIELDS.map((field) => {
          const value = String(record[field] ?? '') || '—';
          const otherValue = highlightDifferentFrom
            ? String(highlightDifferentFrom[field] ?? '') || '—'
            : null;
          const isDifferent = otherValue != null && otherValue !== value;
          return (
            <div key={field} className="flex items-baseline gap-3 px-5 py-2.5">
              <dt className="w-40 shrink-0 text-overline text-slate-400 dark:text-slate-500">
                {FIELD_LABELS[field] || field}
              </dt>
              <dd
                className={[
                  'min-w-0 flex-1 truncate text-[13px]',
                  isDifferent
                    ? 'font-semibold text-red-700 dark:text-red-400'
                    : 'text-slate-800 dark:text-slate-200',
                ].join(' ')}
              >
                {value}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

export default function MergeRecordsPage() {
  const { entityType, winnerId, loserId } = useParams<{
    entityType: string;
    winnerId: string;
    loserId: string;
  }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery<{ data: MergePreviewData }>({
    queryKey: ['merge-preview', entityType, winnerId, loserId],
    queryFn: () =>
      duplicatesApi.mergePreview({
        entity_type: entityType,
        winner_id: Number(winnerId),
        loser_id: Number(loserId),
      }),
    enabled: Boolean(entityType && winnerId && loserId),
  });

  const mergeMutation = useMutation({
    mutationFn: () =>
      duplicatesApi.merge({
        entity_type: entityType,
        winner_id: Number(winnerId),
        loser_id: Number(loserId),
      }),
    onSuccess: () => {
      toast.success('Kayıtlar başarıyla birleştirildi');
      // R4-CACHE-105 — full sweep. The loser id is referenced from
      // many caches (lists, detail pages, activity timelines) and a
      // merge is rare enough that a global invalidate is cheaper than
      // enumerating every key.
      onRecordsMerged(queryClient);
      navigate(`/customers/${winnerId}`);
    },
    onError: () => {
      toast.error('Birleştirme işlemi başarısız oldu');
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner />
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Kayıt Birleştirme" />
        <QueryErrorBanner
          variant="block"
          description="Önizleme yüklenemedi. Kayıtlar bulunamadı."
          onRetry={() => refetch()}
          secondaryAction={{ label: 'Geri Dön', onClick: () => navigate(-1) }}
        />
      </div>
    );
  }

  if (!data?.data) {
    return (
      <div>
        <PageHeader title="Kayıt Birleştirme" />
        <div className="rounded-2xl border border-slate-200 bg-white py-16 text-center shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <p className="text-[14px] text-slate-500 dark:text-slate-400">
            Önizleme yüklenemedi. Kayıtlar bulunamadı.
          </p>
          <div className="mt-4">
            <Button variant="secondary" onClick={() => navigate(-1)}>
              <ArrowLeft size={14} />
              Geri Dön
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const preview = data.data;
  const { winner, loser, related_counts: relatedCounts } = preview;

  const transferSummaryParts = Object.entries(relatedCounts)
    .filter(([, count]) => count > 0)
    .map(([key, count]) => `${count} ${RELATED_LABELS[key] || key}`);

  const transferSummary =
    transferSummaryParts.length > 0
      ? transferSummaryParts.join(', ') + ' aktarılacak'
      : 'Aktarılacak ilişkili kayıt bulunmuyor';

  return (
    <div>
      <PageHeader
        title="Kayıt Birleştirme"
        description={`${entityType === 'customer' ? 'Müşteri' : 'Lead'} kayıtlarını birleştir`}
      >
        <Button variant="secondary" onClick={() => navigate(-1)}>
          <ArrowLeft size={14} />
          Geri Dön
        </Button>
      </PageHeader>

      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <RecordCard title="Kazanan Kayıt" record={winner} variant="winner" />
          <RecordCard
            title="Kaybeden Kayıt"
            record={loser}
            variant="loser"
            highlightDifferentFrom={winner}
          />
        </div>

        {/* Related records summary */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-overline text-slate-500 dark:text-slate-400">İlişkili Kayıtlar</h3>
          {Object.keys(relatedCounts).length === 0 ? (
            <p className="mt-2 text-[13px] text-slate-500 dark:text-slate-400">{transferSummary}</p>
          ) : (
            <>
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(relatedCounts).map(([key, count]) => (
                  <Badge key={key} variant={count > 0 ? 'info' : 'default'} size="md">
                    <span className="text-slate-700 dark:text-slate-200">
                      {RELATED_LABELS[key] || key}
                    </span>
                    <span className="ml-1.5 inline-flex h-5 min-w-[22px] items-center justify-center rounded-full bg-white px-1.5 text-[10px] font-bold tabular-nums ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
                      {count}
                    </span>
                  </Badge>
                ))}
              </div>
              <p className="mt-3 text-[12px] text-slate-500 dark:text-slate-400">
                {transferSummary}
              </p>
            </>
          )}
        </div>

        <div className="flex justify-end">
          <Button
            variant="danger"
            onClick={() => setIsConfirmOpen(true)}
            loading={mergeMutation.isPending}
          >
            Birleştir
          </Button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        onClose={() => setIsConfirmOpen(false)}
        onConfirm={() => {
          mergeMutation.mutate();
          setIsConfirmOpen(false);
        }}
        title="Birleştirme Onayı"
        message={`"${loser.name}" kaydı silinecek ve tüm ilişkili kayıtlar "${winner.name}" kaydına aktarılacak. Bu işlem geri alınamaz.`}
        confirmLabel="Birleştir"
        confirmVariant="danger"
        isLoading={mergeMutation.isPending}
      />
    </div>
  );
}
