import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { analyticsApi } from '../../lib/api';
import type { DataQualityOverview } from '../../lib/types';

const SCORE_THRESHOLDS = {
  good: 75,
  fair: 50,
};

function getCircleColor(score: number): string {
  if (score >= SCORE_THRESHOLDS.good) return '#10b981';
  if (score >= SCORE_THRESHOLDS.fair) return '#f59e0b';
  return '#ef4444';
}

function getBarColor(pct: number): string {
  if (pct >= SCORE_THRESHOLDS.good) return 'bg-emerald-500';
  if (pct >= SCORE_THRESHOLDS.fair) return 'bg-amber-500';
  return 'bg-red-500';
}

function getScoreLabel(score: number): string {
  if (score >= SCORE_THRESHOLDS.good) return 'İyi';
  if (score >= SCORE_THRESHOLDS.fair) return 'Orta';
  return 'Düşük';
}

function getScoreTone(score: number): { text: string; chip: string } {
  if (score >= SCORE_THRESHOLDS.good) {
    return {
      text: 'text-emerald-700 dark:text-emerald-400',
      chip: 'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:ring-emerald-900/40',
    };
  }
  if (score >= SCORE_THRESHOLDS.fair) {
    return {
      text: 'text-amber-700 dark:text-amber-400',
      chip: 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-950/30 dark:ring-amber-900/40',
    };
  }
  return {
    text: 'text-red-700 dark:text-red-400',
    chip: 'bg-red-50 text-red-700 ring-red-100 dark:bg-red-950/30 dark:ring-red-900/40',
  };
}

/**
 * CompletenessCard — KPI tile with circular progress + tone chip.
 *
 * Layout intentionally avoids a separate "Düşük/Orta/İyi" word column on the
 * right; the tone chip carries that information and saves a row of space.
 */
function CompletenessCard({ label, pct }: { label: string; pct: number }) {
  const rounded = Math.round(pct);
  const circ = 97.4;
  const dash = (rounded / 100) * circ;
  const tone = getScoreTone(rounded);
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <p className="text-overline text-slate-500 dark:text-slate-400">{label}</p>
      <div className="mt-3 flex items-center gap-4">
        <div className="relative h-16 w-16 shrink-0">
          <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90" aria-hidden="true">
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e2e8f0" strokeWidth="3" />
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
          <span className="absolute inset-0 flex items-center justify-center text-[15px] font-bold tabular-nums text-slate-900 dark:text-white">
            {rounded}
          </span>
        </div>
        <div className="min-w-0">
          <span
            className={[
              'inline-flex h-6 items-center rounded-full px-2 text-[12px] font-semibold ring-1 ring-inset',
              tone.chip,
            ].join(' ')}
          >
            {getScoreLabel(rounded)}
          </span>
          <p className="mt-1.5 text-[12px] text-slate-500 dark:text-slate-400">
            {rounded < SCORE_THRESHOLDS.fair
              ? 'Acil iyileştirme gerekli'
              : rounded < SCORE_THRESHOLDS.good
                ? 'İyileştirme önerilir'
                : 'Kayıtlar sağlıklı'}
          </p>
        </div>
      </div>
    </div>
  );
}

interface MissingFieldRow {
  label: string;
  missing: number;
  total: number;
}

/**
 * MissingFieldBar — labeled progress bar showing fill percentage.
 *
 * Displays count + label on the right; tabular-nums keeps stacked rows
 * aligned even when one row reads "Tamam" and another "127 eksik".
 */
function MissingFieldBar({ label, missing, total }: MissingFieldRow) {
  const presentPct = total > 0 ? ((total - missing) / total) * 100 : 100;
  return (
    <div className="flex items-center gap-3">
      <span className="w-40 shrink-0 text-[13px] font-medium text-slate-700 dark:text-slate-300">
        {label}
      </span>
      <div className="flex-1">
        <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <div
            className={`h-full rounded-full transition-all ${getBarColor(presentPct)}`}
            style={{ width: `${Math.min(presentPct, 100)}%` }}
          />
        </div>
      </div>
      <span className="w-24 shrink-0 text-right text-[12px] tabular-nums">
        {missing > 0 ? (
          <span className="font-medium text-red-600 dark:text-red-400">{missing} eksik</span>
        ) : (
          <span className="font-medium text-emerald-600 dark:text-emerald-400">Tamam</span>
        )}
      </span>
    </div>
  );
}

export default function DataQualityPage() {
  const {
    data: qualityData,
    isLoading,
    isError,
    refetch,
  } = useQuery<DataQualityOverview>({
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
    <div>
      <PageHeader
        title="Veri Kalitesi"
        description="Müşteri ve teklif kayıtlarındaki eksiklikleri gözden geçir"
      />

      {isError ? (
        <QueryErrorBanner variant="block" onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-[120px] rounded-2xl" />
            ))}
          </div>
          <Skeleton variant="card" />
        </div>
      ) : !qualityData ? (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<AlertCircle size={20} />}
            title="Veri bulunamadı"
            description="Sistem henüz veri kalitesi raporu oluşturmadı."
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <CompletenessCard label="Müşteri Tamamlanma" pct={customerPct} />
            <CompletenessCard label="Teklif Tamamlanma" pct={quotePct} />
            <CompletenessCard label="Genel Ortalama" pct={overallPct} />
          </div>

          {/* Field Completion Rates */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-heading-3 text-slate-900 dark:text-white">
              Alan Tamamlanma Oranları
            </h2>

            {customerFields.length > 0 && (
              <div className="mt-5">
                <p className="mb-3 flex items-center gap-2 text-overline text-slate-500 dark:text-slate-400">
                  Müşteri Alanları
                  <span className="inline-flex h-5 min-w-[28px] items-center justify-center rounded-full bg-slate-100 px-1.5 text-[10px] font-bold tabular-nums text-slate-700 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700">
                    {customers?.total ?? 0}
                  </span>
                </p>
                <div className="space-y-3">
                  {customerFields.map((row) => (
                    <MissingFieldBar key={row.label} {...row} />
                  ))}
                </div>
              </div>
            )}

            {quoteFields.length > 0 && (
              <div className="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800">
                <p className="mb-3 flex items-center gap-2 text-overline text-slate-500 dark:text-slate-400">
                  Teklif Alanları
                  <span className="inline-flex h-5 min-w-[28px] items-center justify-center rounded-full bg-slate-100 px-1.5 text-[10px] font-bold tabular-nums text-slate-700 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700">
                    {quotes?.total ?? 0}
                  </span>
                </p>
                <div className="space-y-3">
                  {quoteFields.map((row) => (
                    <MissingFieldBar key={row.label} {...row} />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Worst Records — pointer to deeper analysis */}
          <div className="rounded-2xl border border-amber-100 bg-amber-50/50 p-5 dark:border-amber-900/40 dark:bg-amber-950/20">
            <div className="flex items-start gap-3">
              <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
                <AlertCircle size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold text-amber-900 dark:text-amber-200">
                  En Eksik Kayıtlar
                </p>
                <p className="mt-0.5 text-[13px] leading-5 text-amber-800/90 dark:text-amber-300/80">
                  Kayıt bazlı veri kalitesi analizi için{' '}
                  <Link to="/reports" className="font-medium underline-offset-2 hover:underline">
                    rapor oluşturun
                  </Link>
                  .
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
