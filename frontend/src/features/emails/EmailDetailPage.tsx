import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { emailsApi, quotesApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import {
  CATEGORY_LABELS,
  REVIEW_STATUS_LABELS,
  REVIEW_STATUS_COLORS,
  STATUS_LABELS,
  STATUS_COLORS,
} from '../../lib/constants';
import type { EmailRequest, MatchResult } from '../../lib/types';

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  let colorClass = 'bg-red-100 text-red-700';
  if (pct >= 80) colorClass = 'bg-green-100 text-green-700';
  else if (pct >= 50) colorClass = 'bg-yellow-100 text-yellow-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${colorClass}`}
    >
      %{pct}
    </span>
  );
}

export default function EmailDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const emailId = Number(id);

  const { data: email, isLoading } = useQuery<EmailRequest>({
    queryKey: ['email', emailId],
    queryFn: () => emailsApi.getEmail(emailId),
    enabled: !!emailId,
  });

  const { data: matches, isLoading: matchesLoading } = useQuery<MatchResult[]>({
    queryKey: ['email-matches', emailId],
    queryFn: () => emailsApi.getEmailMatches(emailId),
    enabled: !!emailId,
  });

  const reparseMutation = useMutation({
    mutationFn: () => emailsApi.reparseEmail(emailId),
    onSuccess: () => {
      toast.success('Email yeniden ayristirildi');
      queryClient.invalidateQueries({ queryKey: ['email', emailId] });
      queryClient.invalidateQueries({ queryKey: ['email-matches', emailId] });
    },
    onError: () => toast.error('Yeniden ayristirma basarisiz'),
  });

  const reviewMutation = useMutation({
    mutationFn: (action: string) => emailsApi.reviewEmail(emailId, action),
    onSuccess: () => {
      toast.success('Inceleme durumu guncellendi');
      queryClient.invalidateQueries({ queryKey: ['email', emailId] });
    },
    onError: () => toast.error('Inceleme guncellenemedi'),
  });

  const createQuoteMutation = useMutation({
    mutationFn: () => quotesApi.createQuoteFromEmail(emailId),
    onSuccess: (quote) => {
      toast.success('Teklif olusturuldu');
      navigate(`/quotes/${quote.id}`);
    },
    onError: () => toast.error('Teklif olusturulamadi'),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton variant="card" count={2} />
      </div>
    );
  }

  if (!email) {
    return (
      <div className="py-16 text-center text-gray-500">Email bulunamadi</div>
    );
  }

  const parsed = email.parsed_data;
  const rs = email.review_status;

  return (
    <div>
      {/* Review Status Banner */}
      {rs && (
        <div
          className={`mb-4 flex items-center justify-between rounded-lg px-4 py-3 ${
            REVIEW_STATUS_COLORS[rs] || 'bg-gray-100 text-gray-700'
          }`}
        >
          <span className="text-sm font-medium">
            Inceleme Durumu: {REVIEW_STATUS_LABELS[rs] || rs}
          </span>
        </div>
      )}

      <PageHeader title={email.subject || '(Konu yok)'}>
        <Button variant="secondary" onClick={() => navigate('/emails')}>
          Geri Don
        </Button>
        <Button
          variant="secondary"
          loading={reparseMutation.isPending}
          onClick={() => reparseMutation.mutate()}
        >
          Yeniden Parse Et
        </Button>
        <Button
          loading={createQuoteMutation.isPending}
          onClick={() => createQuoteMutation.mutate()}
        >
          Teklif Olustur
        </Button>
        {rs !== 'approved' && (
          <Button
            variant="secondary"
            loading={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate('approved')}
            className="!bg-green-600 !text-white hover:!bg-green-700"
          >
            Onayla
          </Button>
        )}
        {rs !== 'rejected' && (
          <Button
            variant="danger"
            loading={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate('rejected')}
          >
            Reddet
          </Button>
        )}
      </PageHeader>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left: Original Email */}
        <Card title="Orijinal Email">
          <div className="space-y-3">
            <div className="grid grid-cols-[100px_1fr] gap-2 text-sm">
              <span className="font-medium text-gray-500">Gonderen:</span>
              <span className="text-gray-900">{email.from_address}</span>
              <span className="font-medium text-gray-500">Konu:</span>
              <span className="text-gray-900">{email.subject}</span>
              <span className="font-medium text-gray-500">Tarih:</span>
              <span className="text-gray-900">
                {formatDateTime(email.received_at || email.created_at)}
              </span>
              <span className="font-medium text-gray-500">Durum:</span>
              <span>
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    STATUS_COLORS[email.status] || 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {STATUS_LABELS[email.status] || email.status}
                </span>
              </span>
            </div>
            <hr className="border-gray-200" />
            <div className="max-h-96 overflow-y-auto whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
              {email.body_text || '(Icerik yok)'}
            </div>
          </div>
        </Card>

        {/* Right: AI Parse Results */}
        <Card title="AI Ayristirma Sonuclari">
          {parsed ? (
            <div className="space-y-4">
              <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
                <span className="font-medium text-gray-500">Kategori:</span>
                <span className="text-gray-900">
                  {CATEGORY_LABELS[parsed.category] || parsed.category || '-'}
                </span>
                <span className="font-medium text-gray-500">Guven Skoru:</span>
                <span>
                  {email.category_confidence != null ? (
                    <ScoreBadge score={email.category_confidence} />
                  ) : (
                    '-'
                  )}
                </span>
                <span className="font-medium text-gray-500">Dil:</span>
                <span className="text-gray-900">{parsed.language || '-'}</span>
                <span className="font-medium text-gray-500">Musteri:</span>
                <span className="text-gray-900">
                  {parsed.customer_name || '-'}
                </span>
                <span className="font-medium text-gray-500">Sirket:</span>
                <span className="text-gray-900">
                  {parsed.customer_company || '-'}
                </span>
                <span className="font-medium text-gray-500">Yedek Parca:</span>
                <span className="text-gray-900">
                  {parsed.is_spare_part_request ? 'Evet' : 'Hayir'}
                </span>
              </div>

              {/* Extracted Parts */}
              {parsed.parts && parsed.parts.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold text-gray-700">
                    Cikarilan Parcalar ({parsed.parts.length})
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 bg-gray-50">
                          <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                            Kod
                          </th>
                          <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                            Aciklama
                          </th>
                          <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                            Adet
                          </th>
                          <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                            Aciliyet
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {parsed.parts.map((part, idx) => (
                          <tr key={idx} className="border-b border-gray-100">
                            <td className="px-3 py-2 font-mono text-xs">
                              {part.part_code}
                            </td>
                            <td className="px-3 py-2">{part.part_description}</td>
                            <td className="px-3 py-2">{part.quantity}</td>
                            <td className="px-3 py-2">{part.urgency || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-500">
              {email.status === 'parsing'
                ? 'Ayristirma devam ediyor...'
                : 'Ayristirma sonucu bulunamadi'}
            </p>
          )}
        </Card>
      </div>

      {/* Part Matching Results */}
      <div className="mt-6">
        <Card title="Parca Eslestirme Sonuclari">
          {matchesLoading ? (
            <Skeleton variant="table" />
          ) : matches && matches.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                      Honeywell Kodu
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                      Isim
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                      Skor
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-gray-500">
                      Strateji
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((m, idx) => (
                    <tr
                      key={idx}
                      className="border-b border-gray-100 hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 font-mono text-xs font-semibold">
                        {m.honeywell_code}
                      </td>
                      <td className="px-4 py-3">{m.name}</td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={m.score} />
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {m.strategy}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-500">
              Eslestirme sonucu bulunamadi
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
