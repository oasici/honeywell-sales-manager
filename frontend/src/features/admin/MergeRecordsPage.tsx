import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { LoadingSpinner } from '../../components/ui/LoadingSpinner';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
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
  name: 'Isim',
  company: 'Sirket',
  email: 'Email',
  phone: 'Telefon',
  address: 'Adres',
  tax_id: 'Vergi No',
  preferred_lang: 'Tercih Edilen Dil',
  created_at: 'Olusturma Tarihi',
};

const RELATED_LABELS: Record<string, string> = {
  quotes: 'Teklif',
  opportunities: 'Firsat',
  emails: 'Email',
  activities: 'Aktivite',
  team_members: 'Takim Uyesi',
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

export default function MergeRecordsPage() {
  const { entityType, winnerId, loserId } = useParams<{
    entityType: string;
    winnerId: string;
    loserId: string;
  }>();
  const navigate = useNavigate();
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  const { data, isLoading, isError } = useQuery<{ data: MergePreviewData }>({
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
      toast.success('Kayitlar basariyla birlestirildi');
      navigate(`/customers/${winnerId}`);
    },
    onError: () => {
      toast.error('Birlestirme islemi basarisiz oldu');
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !data?.data) {
    return (
      <div className="py-20 text-center text-gray-500">
        Onizleme yuklenemedi. Kayitlar bulunamadi.
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
      ? transferSummaryParts.join(', ') + ' aktarilacak'
      : 'Aktarilacak iliskili kayit bulunmuyor';

  return (
    <div className="space-y-6">
      <PageHeader
        title="Kayit Birlestirme"
        description={`${entityType === 'customer' ? 'Musteri' : 'Lead'} kayitlarini birlestir`}
      >
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Geri Don
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Winner Card */}
        <Card>
          <div className="border-b-2 border-green-500 px-5 py-3">
            <h3 className="text-base font-semibold text-green-700">
              Kazanan Kayit (Korunacak)
            </h3>
          </div>
          <div className="divide-y divide-gray-100">
            {DISPLAY_FIELDS.map((field) => (
              <div key={field} className="flex items-center px-5 py-3">
                <span className="w-40 shrink-0 text-sm font-medium text-gray-500">
                  {FIELD_LABELS[field] || field}
                </span>
                <span className="text-sm text-gray-900">
                  {String(winner[field] ?? '') || '-'}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Loser Card */}
        <Card>
          <div className="border-b-2 border-red-500 px-5 py-3">
            <h3 className="text-base font-semibold text-red-700">
              Kaybeden Kayit (Silinecek)
            </h3>
          </div>
          <div className="divide-y divide-gray-100">
            {DISPLAY_FIELDS.map((field) => {
              const winnerVal = String(String(winner[field] ?? '') || '');
              const loserVal = String(String(loser[field] ?? '') || '');
              const isDifferent = winnerVal !== loserVal;
              return (
                <div key={field} className="flex items-center px-5 py-3">
                  <span className="w-40 shrink-0 text-sm font-medium text-gray-500">
                    {FIELD_LABELS[field] || field}
                  </span>
                  <span
                    className={`text-sm ${isDifferent ? 'text-red-700 font-medium' : 'text-gray-900'}`}
                  >
                    {String(loser[field] ?? '') || '-'}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Related Records Summary */}
      <Card>
        <div className="px-5 py-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Iliskili Kayitlar
          </h3>
          <div className="flex flex-wrap gap-4">
            {Object.entries(relatedCounts).map(([key, count]) => (
              <div
                key={key}
                className="flex items-center gap-2 rounded-lg bg-gray-50 px-4 py-2"
              >
                <span className="text-sm text-gray-600">
                  {RELATED_LABELS[key] || key}:
                </span>
                <span className="text-sm font-bold text-gray-900">{count}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-sm text-gray-500">{transferSummary}</p>
        </div>
      </Card>

      {/* Merge Button */}
      <div className="flex justify-end">
        <Button
          onClick={() => setIsConfirmOpen(true)}
          loading={mergeMutation.isPending}
          className="px-8"
        >
          Birlestir
        </Button>
      </div>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        onClose={() => setIsConfirmOpen(false)}
        onConfirm={() => {
          mergeMutation.mutate();
          setIsConfirmOpen(false);
        }}
        title="Birlestirme Onayi"
        message={`"${loser.name}" kaydi silinecek ve tum iliskili kayitlar "${winner.name}" kaydina aktarilacak. Bu islem geri alinamaz.`}
        confirmLabel="Birlestir"
        confirmVariant="danger"
        isLoading={mergeMutation.isPending}
      />
    </div>
  );
}
