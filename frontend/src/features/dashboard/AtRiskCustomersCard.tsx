import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { customerHealthApi } from '../../lib/api';
import type { AtRiskResponse } from '../../lib/types';

function getScoreColor(score: number): string {
  if (score >= 70) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

export function AtRiskCustomersCard() {
  const navigate = useNavigate();
  const { data: atRiskData } = useQuery<AtRiskResponse>({
    queryKey: ['at-risk-customers'],
    queryFn: () => customerHealthApi.getAtRiskCustomers(5),
  });

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-gray-500">
        Risk Altindaki Musteriler
      </h3>
      {atRiskData && atRiskData.customers.length > 0 ? (
        <div className="space-y-2">
          {atRiskData.customers.map((c) => {
            const isChurning = c.risk_level === 'churning';
            const scoreColor = getScoreColor(c.score);
            return (
              <button
                key={c.customer_id}
                type="button"
                onClick={() => navigate(`/customers/${c.customer_id}`)}
                className="flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors hover:bg-gray-50"
                style={{ borderLeftWidth: 4, borderLeftColor: scoreColor }}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-gray-900 truncate">
                    {c.company || c.customer_name}
                  </p>
                  {c.company && (
                    <p className="text-xs text-gray-400 truncate">{c.customer_name}</p>
                  )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      isChurning ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    {isChurning ? 'Kayip Riski' : 'Risk Altinda'}
                  </span>
                  <div className="h-6 w-6 rounded-full border-2 flex items-center justify-center" style={{ borderColor: scoreColor }}>
                    <span className="text-[10px] font-bold" style={{ color: scoreColor }}>
                      {c.score}
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-gray-400">
          Risk altinda musteri bulunmuyor
        </p>
      )}
    </div>
  );
}
