import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { emailsApi, quotesApi, aiApi } from '../../lib/api';
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
  let colorClass = 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300';
  if (pct >= 80)
    colorClass = 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300';
  else if (pct >= 50)
    colorClass = 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${colorClass}`}
    >
      %{pct}
    </span>
  );
}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  let barColor = 'bg-red-500';
  if (pct >= 80) barColor = 'bg-green-500';
  else if (pct >= 50) barColor = 'bg-yellow-500';
  return (
    <div className="flex items-center gap-3">
      <div className="h-2.5 flex-1 rounded-full bg-gray-200 dark:bg-gray-700">
        <div
          className={`h-2.5 rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-bold text-gray-700 dark:text-gray-300">%{pct}</span>
    </div>
  );
}

const STRATEGY_STYLES: Record<string, { label: string; color: string }> = {
  exact_code: {
    label: 'Tam Eslesme',
    color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  },
  exact_model: {
    label: 'Model Eslesme',
    color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  },
  prefix_code: {
    label: 'Prefix',
    color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  },
  fuzzy_code: {
    label: 'Fuzzy Kod',
    color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  },
  fuzzy_name: {
    label: 'Fuzzy Isim',
    color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  },
  semantic: {
    label: 'Semantik',
    color: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  },
};

function StrategyBadge({ strategy }: { strategy: string }) {
  const s = STRATEGY_STYLES[strategy] || { label: strategy, color: 'bg-gray-100 text-gray-600' };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${s.color}`}
    >
      {s.label}
    </span>
  );
}

const URGENCY_COLORS: Record<string, string> = {
  critical: 'bg-red-600 text-white',
  urgent: 'bg-orange-500 text-white',
  normal: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
};

export default function EmailDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const emailId = Number(id);

  const [draftModalOpen, setDraftModalOpen] = useState(false);
  const [draftText, setDraftText] = useState('');

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

  const draftReplyMutation = useMutation({
    mutationFn: () =>
      aiApi.draftReply({ email_id: emailId, draft_type: 'reply', tone: 'professional' }),
    onSuccess: (result: { draft?: string; text?: string }) => {
      const text = result?.draft ?? result?.text ?? '';
      setDraftText(text);
      setDraftModalOpen(true);
    },
    onError: () => toast.error('AI yanit onerisi olusturulamadi'),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton variant="card" count={2} />
      </div>
    );
  }

  if (!email) {
    return <div className="py-16 text-center text-gray-500">Email bulunamadi</div>;
  }

  const parsed = email.parsed_data;
  const rs = email.review_status;

  return (
    <div>
      {/* Review Status Banner with gradient accent */}
      {rs && (
        <div
          className={`mb-4 flex items-center gap-3 overflow-hidden rounded-lg ${
            REVIEW_STATUS_COLORS[rs] || 'bg-gray-100 text-gray-700'
          }`}
        >
          <div
            className={`w-1.5 self-stretch ${
              rs === 'approved'
                ? 'bg-green-500'
                : rs === 'rejected'
                  ? 'bg-red-500'
                  : 'bg-yellow-500'
            }`}
          />
          <span className="py-3 text-sm font-medium">
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
        <Button
          variant="secondary"
          loading={draftReplyMutation.isPending}
          onClick={() => draftReplyMutation.mutate()}
          className="inline-flex items-center gap-1.5"
        >
          <Sparkles size={15} />
          AI Yanit Onerisi
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
                    <ConfidenceBar score={email.category_confidence} />
                  ) : (
                    '-'
                  )}
                </span>
                <span className="font-medium text-gray-500">Dil:</span>
                <span className="text-gray-900">{parsed.language || '-'}</span>
                <span className="font-medium text-gray-500">Musteri:</span>
                <span className="text-gray-900">{parsed.customer_name || '-'}</span>
                <span className="font-medium text-gray-500">Sirket:</span>
                <span className="text-gray-900">{parsed.customer_company || '-'}</span>
                <span className="font-medium text-gray-500">Yedek Parca:</span>
                <span className="text-gray-900">
                  {parsed.is_spare_part_request ? 'Evet' : 'Hayir'}
                </span>
              </div>

              {/* Extracted Parts — card layout */}
              {parsed.parts && parsed.parts.length > 0 && (
                <div>
                  <h4 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Cikarilan Parcalar ({parsed.parts.length})
                  </h4>
                  <div className="space-y-2">
                    {parsed.parts.map((part, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800"
                      >
                        <div className="min-w-0 flex-1">
                          {part.part_code && (
                            <span className="font-mono text-sm font-bold text-gray-900 dark:text-white">
                              {part.part_code}
                            </span>
                          )}
                          <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400 truncate">
                            {part.part_description}
                          </p>
                        </div>
                        <div className="ml-4 flex shrink-0 items-center gap-2">
                          <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                            x{part.quantity}
                          </span>
                          {part.urgency && (
                            <span
                              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${URGENCY_COLORS[part.urgency] || URGENCY_COLORS.normal}`}
                            >
                              {part.urgency}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
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

      {/* AI Draft Reply Modal */}
      <Modal
        isOpen={draftModalOpen}
        onClose={() => setDraftModalOpen(false)}
        title="AI Yanit Onerisi"
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Asagidaki taslagi duzenleyebilir, ardından kopyalayabilirsiniz.
          </p>
          <textarea
            rows={10}
            className="w-full rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 resize-y"
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
          />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setDraftModalOpen(false)}>
              Kapat
            </Button>
            <Button
              onClick={() => {
                navigator.clipboard
                  .writeText(draftText)
                  .then(() => toast.success('Metin panoya kopyalandi'))
                  .catch(() => toast.error('Kopyalama basarisiz'));
              }}
            >
              Kopyala
            </Button>
          </div>
        </div>
      </Modal>

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
                      className="border-b border-gray-100 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                    >
                      <td className="px-4 py-3 font-mono text-xs font-semibold">
                        {m.honeywell_code}
                      </td>
                      <td className="px-4 py-3">{m.name}</td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={m.score} />
                      </td>
                      <td className="px-4 py-3">
                        <StrategyBadge strategy={m.strategy} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-500">Eslestirme sonucu bulunamadi</p>
          )}
        </Card>
      </div>
    </div>
  );
}
