import { useQuery } from '@tanstack/react-query';
import { BarChart2, AlertCircle } from 'lucide-react';
import { analyticsApi } from '../../lib/api';
import type { DataQualityOverview } from '../../lib/types';

const SCORE_THRESHOLDS = {
  good: 75,
  fair: 50,
};

function getCircleColor(score: number): string {
  if (score >= SCORE_THRESHOLDS.good) return '#22c55e';
  if (score >= SCORE_THRESHOLDS.fair) return '#eab308';
  return '#ef4444';
}

function getBarColor(pct: number): string {
  if (pct >= SCORE_THRESHOLDS.good) return 'bg-green-500';
  if (pct >= SCORE_THRESHOLDS.fair) return 'bg-yellow-500';
  return 'bg-red-500';
}

function getScoreLabel(score: number): string {
  if (score >= SCORE_THRESHOLDS.good) return 'Iyi';
  if (score >= SCORE_THRESHOLDS.fair) return 'Orta';
  return 'Düşük';
}

function getScoreTextClass(score: number): string {
  if (score >= SCORE_THRESHOLDS.good) return 'text-green-600';
  if (score >= SCORE_THRESHOLDS.fair) return 'text-yellow-600';
  return 'text-red-600';
}

function CompletenessCard({ label, pct }: { label: string; pct: number }) {
  const rounded = Math.round(pct);
  const circ = 97.4;
  const dash = (rounded / 100) * circ;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <div className="mt-3 flex items-center gap-4">
        <div className="relative h-16 w-16">
          <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90" aria-hidden="true">
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e5e7eb" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r="15.5"
              fill="none"
              stroke={getCircleColor(rounded)}
              strokeWidth="3"
              strokeDasharray={`${dash} ${circ - dash}`}
              strokeLinecap="round"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-gray-900">
            {rounded}
          </span>
        </div>
        <p className={`text-sm font-medium ${getScoreTextClass(rounded)}`}>
          {getScoreLabel(rounded)}
        </p>
      </div>
    </div>
  );
}

interface MissingFieldRow {
  label: string;
  missing: number;
  total: number;
}

function MissingFieldBar({ label, missing, total }: MissingFieldRow) {
  const presentPct = total > 0 ? ((total - missing) / total) * 100 : 100;
  return (
    <div className="flex items-center gap-3">
      <span className="w-40 text-sm text-gray-600 shrink-0">{label}</span>
      <div className="flex-1">
        <div className="h-5 overflow-hidden rounded-full bg-gray-100">
          <div
            className={`h-full rounded-full transition-all ${getBarColor(presentPct)}`}
            style={{ width: `${Math.min(presentPct, 100)}%` }}
          />
        </div>
      </div>
      <span className="w-20 text-right text-sm text-gray-500 shrink-0">
        {missing > 0 ? (
          <span className="text-red-500 font-medium">{missing} eksik</span>
        ) : (
          <span className="text-green-600 font-medium">Tamam</span>
        )}
      </span>
    </div>
  );
}

export default function DataQualityPage() {
  const { data: qualityData, isLoading } = useQuery<DataQualityOverview>({
    queryKey: ['data-quality'],
    queryFn: () => analyticsApi.getDataQuality(),
  });

  const customers = qualityData?.customers;
  const quotes = qualityData?.quotes;

  const customerPct = customers?.completeness_pct ?? 0;
  const quotePct = quotes?.completeness_pct ?? 0;
  const overallPct = customerPct > 0 || quotePct > 0 ? (customerPct + quotePct) / 2 : 0;

  const customerFields: MissingFieldRow[] = customers
    ? [
        { label: 'Telefon', missing: customers.missing_phone, total: customers.total },
        { label: 'E-posta', missing: customers.missing_email, total: customers.total },
        { label: 'Firma', missing: customers.missing_company, total: customers.total },
      ]
    : [];

  const quoteFields: MissingFieldRow[] = quotes
    ? [
        { label: 'Müşteri Ataması', missing: quotes.missing_customer, total: quotes.total },
        { label: 'Ürün Kalemleri', missing: quotes.missing_items, total: quotes.total },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <BarChart2 size={24} className="text-honeywell-red" />
        <h1 className="text-2xl font-bold text-gray-900">Veri Kalitesi</h1>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-gray-400">Yükleniyor...</div>
      ) : !qualityData ? (
        <div className="py-12 text-center text-gray-400">Veri bulunamadi</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <CompletenessCard label="Müşteri Tamamlanma" pct={customerPct} />
            <CompletenessCard label="Teklif Tamamlanma" pct={quotePct} />
            <CompletenessCard label="Genel Ortalama" pct={overallPct} />
          </div>

          {/* Field Completion Rates */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">Alan Tamamlanma Oranlari</h2>

            {customerFields.length > 0 && (
              <div className="mb-5">
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
                  Müşteri Alanları ({customers?.total ?? 0} kayıt)
                </p>
                <div className="space-y-3">
                  {customerFields.map((row) => (
                    <MissingFieldBar key={row.label} {...row} />
                  ))}
                </div>
              </div>
            )}

            {quoteFields.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
                  Teklif Alanları ({quotes?.total ?? 0} kayıt)
                </p>
                <div className="space-y-3">
                  {quoteFields.map((row) => (
                    <MissingFieldBar key={row.label} {...row} />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Worst Records — not available from this API */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-lg font-semibold text-gray-900">En Eksik Kayıtlar</h2>
            <div className="flex items-start gap-3 rounded-lg bg-amber-50 border border-amber-200 p-4">
              <AlertCircle size={18} className="text-amber-500 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm text-amber-800 font-medium">Detayli analiz mevcut değil</p>
                <p className="text-sm text-amber-700 mt-0.5">
                  Kayıt bazli veri kalitesi analizi icin{' '}
                  <a href="/reports" className="underline font-medium hover:text-amber-900">
                    rapor olusturun
                  </a>
                  .
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
