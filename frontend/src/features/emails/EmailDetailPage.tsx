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
import { useT } from '../../hooks/useT';
import { REVIEW_STATUS_COLORS, STATUS_COLORS } from '../../lib/constants';
import {
  translateEmailCategory,
  translateReviewStatus,
  translateStatus,
} from '../../lib/labelTranslations';
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
      <div className="h-2.5 flex-1 rounded-full bg-gray-200 dark:bg-slate-800">
        <div
          className={`h-2.5 rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-bold text-slate-700 dark:text-slate-300">%{pct}</span>
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
    label: 'Fuzzy İsim',
    color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
  },
  semantic: {
    label: 'Semantik',
    color: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  },
};

function StrategyBadge({ strategy }: { strategy: string }) {
  const s = STRATEGY_STYLES[strategy] || { label: strategy, color: 'bg-slate-100 text-slate-600' };
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
  normal: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};

export default function EmailDetailPage() {
  const t = useT();
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
      toast.success(t('emails.detail_toast_reparse'));
      queryClient.invalidateQueries({ queryKey: ['email', emailId] });
      queryClient.invalidateQueries({ queryKey: ['email-matches', emailId] });
    },
    onError: () => toast.error(t('emails.detail_toast_reparse_failed')),
  });

  const reviewMutation = useMutation({
    mutationFn: (action: string) => emailsApi.reviewEmail(emailId, action),
    onSuccess: () => {
      toast.success(t('emails.detail_toast_review_updated'));
      queryClient.invalidateQueries({ queryKey: ['email', emailId] });
    },
    onError: () => toast.error(t('emails.detail_toast_review_failed')),
  });

  const createQuoteMutation = useMutation({
    mutationFn: () => quotesApi.createQuoteFromEmail(emailId),
    onSuccess: (quote) => {
      toast.success(t('emails.detail_toast_quote_created'));
      navigate(`/quotes/${quote.id}`);
    },
    onError: () => toast.error(t('emails.detail_toast_quote_failed')),
  });

  const draftReplyMutation = useMutation({
    mutationFn: () =>
      aiApi.draftReply({ email_id: emailId, draft_type: 'reply', tone: 'professional' }),
    onSuccess: (result: { draft?: string; text?: string }) => {
      const text = result?.draft ?? result?.text ?? '';
      setDraftText(text);
      setDraftModalOpen(true);
    },
    onError: () => toast.error(t('emails.detail_toast_ai_failed')),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton variant="card" count={2} />
      </div>
    );
  }

  if (!email) {
    return <div className="py-16 text-center text-slate-500">{t('emails.detail_not_found')}</div>;
  }

  const parsed = email.parsed_data;
  const rs = email.review_status;

  return (
    <div>
      {/* Review Status Banner with gradient accent */}
      {rs && (
        <div
          className={`mb-4 flex items-center gap-3 overflow-hidden rounded-lg ${
            REVIEW_STATUS_COLORS[rs] || 'bg-slate-100 text-slate-700'
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
            {t('emails.detail_review_prefix')}: {translateReviewStatus(rs, t)}
          </span>
        </div>
      )}

      {/* R6-RENDER-3 — KVKK data classification badge. Backend round-trips
          ``data_classification`` since round-4; until now the SPA never
          rendered it, so reps couldn't tell at a glance which messages
          were "restricted" vs "public". */}
      {email.data_classification && email.data_classification !== 'public' && (
        <div
          className={`mb-3 rounded-lg border px-3 py-2 text-[12px] ${
            email.data_classification === 'restricted'
              ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300'
              : email.data_classification === 'confidential'
                ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300'
                : 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300'
          }`}
        >
          <span className="font-semibold uppercase tracking-wider">
            KVKK · {email.data_classification}
          </span>
          <span className="ml-2 opacity-80">
            Bu mesaj sınıflandırılmış veri içerir; paylaşım kısıtlamalarına dikkat ediniz.
          </span>
        </div>
      )}
      {/* R6-RENDER-5 — duplicate-detection affordance. Pre-R6 the parser
          set ``is_duplicate``/``duplicate_of_id`` but the SPA never
          rendered the link, so reps acted on the dup as if it were a
          fresh inquiry. */}
      {email.is_duplicate && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
          <span className="font-semibold">Yinelenen mesaj.</span>
          {email.duplicate_of_id != null ? (
            <button
              type="button"
              onClick={() => navigate(`/emails/${email.duplicate_of_id}`)}
              className="ml-2 underline underline-offset-2 hover:no-underline"
            >
              Orijinali görüntüle (#{email.duplicate_of_id})
            </button>
          ) : (
            <span className="ml-2 opacity-80">
              Aynı içerikli daha önce işlenmiş bir kayıt mevcut.
            </span>
          )}
        </div>
      )}

      <PageHeader title={email.subject || '(Konu yok)'}>
        <Button variant="secondary" onClick={() => navigate('/emails')}>
          {t('emails.detail_back')}
        </Button>
        <Button
          variant="secondary"
          loading={reparseMutation.isPending}
          onClick={() => reparseMutation.mutate()}
        >
          {t('emails.detail_reparse')}
        </Button>
        <Button
          loading={createQuoteMutation.isPending}
          onClick={() => createQuoteMutation.mutate()}
        >
          {t('emails.detail_create_quote')}
        </Button>
        <Button
          variant="secondary"
          loading={draftReplyMutation.isPending}
          onClick={() => draftReplyMutation.mutate()}
          className="inline-flex items-center gap-1.5"
        >
          <Sparkles size={15} />
          {t('emails.detail_ai_draft')}
        </Button>
        {rs !== 'approved' && (
          <Button
            variant="secondary"
            loading={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate('approved')}
            className="!bg-green-600 !text-white hover:!bg-green-700"
          >
            {t('emails.detail_approve')}
          </Button>
        )}
        {rs !== 'rejected' && (
          <Button
            variant="danger"
            loading={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate('rejected')}
          >
            {t('emails.detail_reject')}
          </Button>
        )}
      </PageHeader>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left: Original Email */}
        <Card title={t('emails.detail_original')}>
          <div className="space-y-3">
            <div className="grid grid-cols-[100px_1fr] gap-2 text-sm">
              <span className="font-medium text-slate-500">{t('emails.sender')}:</span>
              <span className="text-slate-900">{email.from_address}</span>
              <span className="font-medium text-slate-500">{t('emails.subject')}:</span>
              <span className="text-slate-900">{email.subject}</span>
              <span className="font-medium text-slate-500">{t('emails.date')}:</span>
              <span className="text-slate-900">
                {formatDateTime(email.received_at || email.created_at)}
              </span>
              <span className="font-medium text-slate-500">{t('common.status')}:</span>
              <span>
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    STATUS_COLORS[email.status] || 'bg-slate-100 text-slate-700'
                  }`}
                >
                  {translateStatus(email.status, t)}
                </span>
              </span>
            </div>
            <hr className="border-slate-200" />
            <div className="max-h-96 overflow-y-auto whitespace-pre-wrap text-sm text-slate-700 leading-relaxed">
              {email.body_text || t('emails.no_content')}
            </div>
          </div>
        </Card>

        {/* Right: AI Parse Results */}
        <Card title={t('emails.detail_parse_results')}>
          {parsed ? (
            <div className="space-y-4">
              <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
                <span className="font-medium text-slate-500">Kategori:</span>
                <span className="text-slate-900">
                  {parsed.category ? translateEmailCategory(parsed.category, t) : '-'}
                </span>
                <span className="font-medium text-slate-500">Guven Skoru:</span>
                <span>
                  {email.category_confidence != null ? (
                    <ConfidenceBar score={email.category_confidence} />
                  ) : (
                    '-'
                  )}
                </span>
                <span className="font-medium text-slate-500">Dil:</span>
                <span className="text-slate-900">{parsed.language || '-'}</span>
                <span className="font-medium text-slate-500">Müşteri:</span>
                <span className="text-slate-900">{parsed.customer_name || '-'}</span>
                <span className="font-medium text-slate-500">Şirket:</span>
                <span className="text-slate-900">{parsed.customer_company || '-'}</span>
                <span className="font-medium text-slate-500">Yedek Parça:</span>
                <span className="text-slate-900">
                  {parsed.is_spare_part_request ? 'Evet' : 'Hayir'}
                </span>
              </div>

              {/* Extracted Parts — card layout */}
              {parsed.parts && parsed.parts.length > 0 && (
                <div>
                  <h4 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Çıkarılan Parçalar ({parsed.parts.length})
                  </h4>
                  <div className="space-y-2">
                    {parsed.parts.map((part, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-800"
                      >
                        <div className="min-w-0 flex-1">
                          {part.part_code && (
                            <span className="font-mono text-sm font-bold text-slate-900 dark:text-white">
                              {part.part_code}
                            </span>
                          )}
                          <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400 truncate">
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
            <p className="py-8 text-center text-sm text-slate-500">
              {email.status === 'parsing'
                ? t('emails.detail_parsing_in_progress')
                : t('emails.detail_parse_none')}
            </p>
          )}
        </Card>
      </div>

      {/* AI Draft Reply Modal */}
      <Modal
        isOpen={draftModalOpen}
        onClose={() => setDraftModalOpen(false)}
        title={t('emails.detail_draft_modal_title')}
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-500">{t('emails.detail_draft_modal_help')}</p>
          <textarea
            rows={10}
            className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-100 resize-y"
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
          />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setDraftModalOpen(false)}>
              {t('common.close')}
            </Button>
            <Button
              onClick={() => {
                navigator.clipboard
                  .writeText(draftText)
                  .then(() => toast.success(t('emails.detail_copy_success')))
                  .catch(() => toast.error(t('emails.detail_copy_failed')));
              }}
            >
              {t('common.copy')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Part Matching Results */}
      <div className="mt-6">
        <Card title={t('emails.detail_match_results')}>
          {matchesLoading ? (
            <Skeleton variant="table" />
          ) : matches && matches.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50">
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                      Honeywell Kodu
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                      İsim
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                      Skor
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold uppercase text-slate-500">
                      Strateji
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((m, idx) => (
                    <tr
                      key={idx}
                      className="border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
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
            <p className="py-8 text-center text-sm text-slate-500">
              {t('emails.detail_match_none')}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
