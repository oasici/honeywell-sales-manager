import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle, XCircle, AlertCircle, PenLine, Clock } from 'lucide-react';
import { signaturesApi } from '../../lib/api';
import type { SignatureRequest } from '../../lib/types';

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
    onError: () => toast.error('Imzalama islemi basarisiz oldu'),
  });

  const declineMutation = useMutation({
    mutationFn: () => signaturesApi.decline(token!),
    onSuccess: () => {
      setIsDeclined(true);
    },
    onError: () => toast.error('Reddetme islemi basarisiz oldu'),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-honeywell-red" />
          <p className="text-sm text-gray-500">Yukleniyor...</p>
        </div>
      </div>
    );
  }

  if (isError || !signRequest) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <AlertCircle className="mx-auto mb-4 h-14 w-14 text-red-400" />
          <h1 className="mb-2 text-xl font-bold text-gray-900">Belge Bulunamadi</h1>
          <p className="text-sm text-gray-500">Bu imza baglantisi gecersiz veya bulunamadi.</p>
        </div>
      </div>
    );
  }

  if (isSigned || signRequest.status === 'signed') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <CheckCircle className="mx-auto mb-4 h-14 w-14 text-green-500" />
          <h1 className="mb-2 text-2xl font-bold text-gray-900">Belge Basariyla Imzalandi</h1>
          <p className="text-sm text-gray-500">{signRequest.signer_email} icin imza kaydedildi.</p>
          {signRequest.signed_at && (
            <p className="mt-2 text-xs text-gray-400">
              Imzalanma tarihi: {new Date(signRequest.signed_at).toLocaleString('tr-TR')}
            </p>
          )}
          <div className="mt-6 rounded-xl bg-green-50 px-4 py-3 text-sm text-green-700">
            Imzaniz basariyla alindi. Tesekkur ederiz.
          </div>
        </div>
      </div>
    );
  }

  if (isDeclined || signRequest.status === 'declined') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <XCircle className="mx-auto mb-4 h-14 w-14 text-red-400" />
          <h1 className="mb-2 text-xl font-bold text-gray-900">Belge Reddedildi</h1>
          <p className="text-sm text-gray-500">Bu belge icin imza talebi reddedildi.</p>
        </div>
      </div>
    );
  }

  if (isExpired(signRequest.expires_at)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
          <Clock className="mx-auto mb-4 h-14 w-14 text-amber-400" />
          <h1 className="mb-2 text-xl font-bold text-gray-900">Bu Imza Suresi Dolmus</h1>
          <p className="text-sm text-gray-500">
            Bu imza baglantisi {new Date(signRequest.expires_at).toLocaleDateString('tr-TR')}{' '}
            tarihinde suresi doldu. Yeni bir imza talebi icin lutfen gondericiye basvurun.
          </p>
        </div>
      </div>
    );
  }

  const documentTypeLabel =
    data?.document_type === 'invoice'
      ? 'Fatura'
      : data?.document_type === 'contract'
        ? 'Kontrat'
        : data?.document_type === 'quote'
          ? 'Teklif'
          : (data?.document_type ?? 'Belge');

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-honeywell-red/10">
            <PenLine className="h-6 w-6 text-honeywell-red" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Belge Imzalama</h1>
          <p className="mt-1 text-sm text-gray-500">
            Asagidaki belgeyi inceleyip imzalayabilirsiniz
          </p>
        </div>

        {/* Document Summary Card */}
        <div className="mb-5 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <div className="mb-4 flex items-start justify-between">
            <div>
              <span className="inline-block rounded-lg bg-honeywell-red/10 px-3 py-1 text-xs font-semibold text-honeywell-red">
                {documentTypeLabel}
              </span>
              {data?.document_id && (
                <p className="mt-1 text-sm text-gray-500">Belge #{data.document_id}</p>
              )}
            </div>
            <div className="text-right text-xs text-gray-400">
              <p>Son gecerlilik</p>
              <p className="font-medium text-gray-600">
                {new Date(signRequest.expires_at).toLocaleDateString('tr-TR')}
              </p>
            </div>
          </div>

          {data?.document_summary && (
            <div className="rounded-xl bg-gray-50 px-4 py-3 text-sm text-gray-700">
              {data.document_summary}
            </div>
          )}

          <div className="mt-4 border-t border-gray-100 pt-4">
            <p className="text-xs text-gray-500">Imzalayan</p>
            <p className="text-sm font-medium text-gray-900">{signRequest.signer_email}</p>
          </div>
        </div>

        {/* Signing Form */}
        <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Imzala</h2>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">Adiniz Soyadiniz</label>
            <input
              type="text"
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-red/20"
              placeholder="Ad Soyad"
              value={signerName}
              onChange={(e) => setSignerName(e.target.value)}
            />
          </div>

          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-gray-300 accent-honeywell-red"
              checked={isAgreed}
              onChange={(e) => setIsAgreed(e.target.checked)}
            />
            <span className="text-sm text-gray-600">
              Bu belgeyi okudum, anladin ve <strong className="text-gray-800">onayliyorum</strong>.
              Dijital imzamın bu belge icin yasal olarak baglayici oldugunu kabul ediyorum.
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
                  Imzalaniyor...
                </>
              ) : (
                <>
                  <CheckCircle className="h-4 w-4" />
                  Imzala
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
                  Reddediliyor...
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4" />
                  Reddet
                </>
              )}
            </button>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-gray-400">
          Bu imza baglantisi yalnizca {signRequest.signer_email} icin gonderilmistir.
        </p>
      </div>
    </div>
  );
}
