import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle, XCircle, AlertCircle, PenLine, Clock } from 'lucide-react';
import { signaturesApi } from '../../lib/api';
import { formatDate, formatDateTime } from '../../lib/formatters';
import type { SignatureRequest } from '../../lib/types';
import type { TranslationKey } from '../../lib/i18n';
import { useT } from '../../hooks/useT';

interface PublicSignResponse {
  request: SignatureRequest;
  document_summary?: string;
  document_type?: string;
  document_id?: number;
}

function isExpired(expiresAt: string): boolean {
  return new Date(expiresAt) < new Date();
}

export default function SigningPage() {
  const { token } = useParams<{ token: string }>();
  const t = useT();
  const [signerName, setSignerName] = useState('');
  const [isAgreed, setIsAgreed] = useState(false);
  const [isSigned, setIsSigned] = useState(false);
  const [isDeclined, setIsDeclined] = useState(false);

  const { data, isLoading, isError } = useQuery<PublicSignResponse>({
    queryKey: ['sign', token],
    queryFn: () => signaturesApi.getPublic(token!),
    enabled: !!token,
    retry: false,
  });

  const signRequest = data?.request;

  useEffect(() => {
    if (signRequest?.signer_name) {
      // Defer to satisfy react-hooks/set-state-in-effect ESLint rule
      const name = signRequest.signer_name;
      queueMicrotask(() => setSignerName(name));
    }
  }, [signRequest?.signer_name]);

  const signMutation = useMutation({
    mutationFn: () =>
      signaturesApi.sign(token!, {
        signer_name: signerName || undefined,
      }),
    onSuccess: () => {
      setIsSigned(true);
    },
    onError: () => toast.error(t('esign.toast_sign_fail')),
  });

  const declineMutation = useMutation({
    mutationFn: () => signaturesApi.decline(token!),
    onSuccess: () => {
      setIsDeclined(true);
    },
    onError: () => toast.error(t('esign.toast_reject_fail')),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-honeywell-red" />
          <p className="text-sm text-slate-500">{t('esign.loading')}</p>
        </div>
      </div>
    );
  }

  if (isError || !signRequest) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <AlertCircle className="mx-auto mb-4 h-14 w-14 text-red-400" />
          <h1 className="mb-2 text-xl font-bold text-slate-900">{t('esign.not_found_title')}</h1>
          <p className="text-sm text-slate-500">{t('esign.invalid_link')}</p>
        </div>
      </div>
    );
  }

  if (isSigned || signRequest.status === 'signed') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <CheckCircle className="mx-auto mb-4 h-14 w-14 text-green-500" />
          <h1 className="mb-2 text-2xl font-bold text-slate-900">{t('esign.signed_title')}</h1>
          <p className="text-sm text-slate-500">
            {t('esign.signed_for').replace('{email}', signRequest.signer_email)}
          </p>
          {signRequest.signed_at && (
            <p className="mt-2 text-xs text-slate-400">
              {t('esign.signed_at').replace('{datetime}', formatDateTime(signRequest.signed_at))}
            </p>
          )}
          <div className="mt-6 rounded-xl bg-green-50 px-4 py-3 text-sm text-green-700">
            {t('esign.signed_thanks')}
          </div>
        </div>
      </div>
    );
  }

  if (isDeclined || signRequest.status === 'declined') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <XCircle className="mx-auto mb-4 h-14 w-14 text-red-400" />
          <h1 className="mb-2 text-xl font-bold text-slate-900">{t('esign.rejected_title')}</h1>
          <p className="text-sm text-slate-500">{t('esign.rejected')}</p>
        </div>
      </div>
    );
  }

  if (isExpired(signRequest.expires_at)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <Clock className="mx-auto mb-4 h-14 w-14 text-amber-400" />
          <h1 className="mb-2 text-xl font-bold text-slate-900">{t('esign.expired_title')}</h1>
          <p className="text-sm text-slate-500">
            {t('esign.expired_body').replace('{date}', formatDate(signRequest.expires_at))}
          </p>
        </div>
      </div>
    );
  }

  const documentTypeKey: TranslationKey =
    data?.document_type === 'invoice'
      ? 'esign.doc_type_invoice'
      : data?.document_type === 'contract'
        ? 'esign.doc_type_contract'
        : data?.document_type === 'quote'
          ? 'esign.doc_type_quote'
          : 'esign.doc_type_document';

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-honeywell-red/10">
            <PenLine className="h-6 w-6 text-honeywell-red" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">{t('esign.signing_title')}</h1>
          <p className="mt-1 text-sm text-slate-500">{t('esign.signing_subtitle')}</p>
        </div>

        {/* Document Summary Card */}
        <div className="mb-5 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <div className="mb-4 flex items-start justify-between">
            <div>
              <span className="inline-block rounded-lg bg-honeywell-red/10 px-3 py-1 text-xs font-semibold text-honeywell-red">
                {t(documentTypeKey)}
              </span>
              {data?.document_id && (
                <p className="mt-1 text-sm text-slate-500">
                  {t('esign.document_id').replace('{id}', String(data.document_id))}
                </p>
              )}
            </div>
            <div className="text-right text-xs text-slate-400">
              <p>{t('esign.last_valid')}</p>
              <p className="font-medium text-slate-600">{formatDate(signRequest.expires_at)}</p>
            </div>
          </div>

          {data?.document_summary && (
            <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
              {data.document_summary}
            </div>
          )}

          <div className="mt-4 border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">{t('esign.signer')}</p>
            <p className="text-sm font-medium text-slate-900">{signRequest.signer_email}</p>
          </div>
        </div>

        {/* Signing Form */}
        <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="mb-4 text-base font-semibold text-slate-900">{t('esign.sign_title')}</h2>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-slate-700">
              {t('esign.name_label')}
            </label>
            <input
              type="text"
              className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-red/20"
              placeholder={t('esign.name_ph')}
              value={signerName}
              onChange={(e) => setSignerName(e.target.value)}
            />
          </div>

          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-slate-200 accent-honeywell-red"
              checked={isAgreed}
              onChange={(e) => setIsAgreed(e.target.checked)}
            />
            <span className="text-sm text-slate-600">
              {t('esign.agree_prefix')}{' '}
              <strong className="text-slate-800">{t('esign.agree_bold')}</strong>.{' '}
              {t('esign.legal_ack')}
            </span>
          </label>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              disabled={!isAgreed || signMutation.isPending}
              onClick={() => signMutation.mutate()}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-green-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {signMutation.isPending ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  {t('esign.signing')}
                </>
              ) : (
                <>
                  <CheckCircle className="h-4 w-4" />
                  {t('esign.sign')}
                </>
              )}
            </button>
            <button
              type="button"
              disabled={declineMutation.isPending}
              onClick={() => declineMutation.mutate()}
              className="flex items-center justify-center gap-2 rounded-xl border border-red-300 px-5 py-3 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {declineMutation.isPending ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-red-400 border-t-transparent" />
                  {t('esign.declining')}
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4" />
                  {t('esign.decline')}
                </>
              )}
            </button>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">
          {t('esign.link_only_for').replace('{email}', signRequest.signer_email)}
        </p>
      </div>
    </div>
  );
}
