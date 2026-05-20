import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { customerHealthApi } from '../../lib/api';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import type { AtRiskResponse } from '../../lib/types';

/**
 * AtRiskCustomersCard — top-N customers with the lowest health scores.
 *
 * Visual:
 *   - Card shell uses the dashboard-standard border/shadow tokens.
 *   - Row treatment is divide-y on slate-100 (Linear pattern) instead of
 *     boxed cards so the list reads as a continuous record set.
 *   - Score chip lives on the right with a brand-tinted ring; the dotted
 *     status Badge sits beside it for a quick churning vs. risk read.
 */
function getScoreTone(score: number): 'critical' | 'warn' | 'ok' {
  if (score >= 70) return 'ok';
  if (score >= 40) return 'warn';
  return 'critical';
}

const SCORE_TONE_CLASSES: Record<'critical' | 'warn' | 'ok', string> = {
  critical: 'bg-red-50 text-red-700 ring-red-100',
  warn: 'bg-amber-50 text-amber-700 ring-amber-100',
  ok: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
};

export function AtRiskCustomersCard() {
  const navigate = useNavigate();
  // Track which row's recommendations are expanded — the API returns
  // 2-3 actionable recommendations per customer (audit F-3) that the
  // previous card silently dropped.
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const {
    data: atRiskData,
    isError,
    refetch,
  } = useQuery<AtRiskResponse>({
    queryKey: ['at-risk-customers'],
    queryFn: () => customerHealthApi.getAtRiskCustomers(5),
  });

  const customers = atRiskData?.customers ?? [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between px-5 pb-3 pt-5">
        <h3 className="text-overline text-slate-500 dark:text-slate-400">
          Risk Altındaki Müşteriler
        </h3>
        {customers.length > 0 && (
          <button
            type="button"
            onClick={() => navigate('/customers/high-intent')}
            className="text-[12px] font-medium text-slate-500 transition-colors hover:text-honeywell-red"
          >
            Tümü
          </button>
        )}
      </div>

      {isError ? (
        <div className="px-5 pb-5">
          <QueryErrorBanner variant="block" onRetry={() => refetch()} />
        </div>
      ) : customers.length === 0 ? (
        <div className="px-5 pb-5">
          <EmptyState
            variant="compact"
            icon={<AlertTriangle size={18} />}
            title="Risk altında müşteri yok"
            description="Tüm sağlık skorları normal aralıkta."
          />
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {customers.map((c) => {
            const tone = getScoreTone(c.score);
            const isChurning = c.risk_level === 'churning';
            const recs = c.recommendations ?? [];
            const isExpanded = expandedId === c.customer_id;
            const hasRecs = recs.length > 0;
            return (
              <li key={c.customer_id}>
                <div className="group flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60">
                  <button
                    type="button"
                    onClick={() => navigate(`/customers/${c.customer_id}`)}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-semibold text-slate-900 dark:text-white">
                        {c.company || c.customer_name}
                      </p>
                      {c.company && (
                        <p className="truncate text-[12px] text-slate-500 dark:text-slate-400">
                          {c.customer_name}
                        </p>
                      )}
                    </div>
                  </button>
                  <Badge variant={isChurning ? 'danger' : 'warning'} size="sm" dot>
                    {isChurning ? 'Kayıp' : 'Risk'}
                  </Badge>
                  <span
                    className={[
                      'inline-flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold tabular-nums ring-1 ring-inset',
                      SCORE_TONE_CLASSES[tone],
                    ].join(' ')}
                    aria-label={`Sağlık skoru ${c.score}`}
                  >
                    {c.score}
                  </span>
                  {hasRecs ? (
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : c.customer_id)}
                      aria-label="Önerileri göster"
                      className="rounded p-0.5 text-slate-300 hover:bg-slate-100 hover:text-slate-500 dark:hover:bg-slate-800"
                    >
                      <ChevronDown
                        size={14}
                        className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                      />
                    </button>
                  ) : (
                    <ChevronRight size={14} className="text-slate-300" />
                  )}
                </div>
                {isExpanded && hasRecs && (
                  <ul className="space-y-0.5 border-t border-slate-100 bg-slate-50/40 px-5 py-2 dark:border-slate-800 dark:bg-slate-900/40">
                    {recs.slice(0, 4).map((r, i) => (
                      <li
                        key={i}
                        className="flex gap-1.5 text-[12px] text-slate-600 dark:text-slate-300"
                      >
                        <span className="text-amber-500">›</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
