import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ChevronRight } from 'lucide-react';
import { customerHealthApi } from '../../lib/api';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
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
  const { data: atRiskData } = useQuery<AtRiskResponse>({
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

      {customers.length === 0 ? (
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
            return (
              <li key={c.customer_id}>
                <button
                  type="button"
                  onClick={() => navigate(`/customers/${c.customer_id}`)}
                  className="group flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
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
                  <ChevronRight
                    size={14}
                    className="text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-slate-500"
                  />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
