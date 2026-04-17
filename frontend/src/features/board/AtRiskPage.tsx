import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, TrendingDown, ChevronRight } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { dealHealthApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';

interface AtRiskOpportunity {
  opportunity_id: number;
  title: string;
  score: number;
  risk_level: string;
  indicators: {
    name: string;
    label: string;
    score: number;
    weight: number;
    raw_value: unknown;
    description: string;
  }[];
  recommendations: string[];
}

interface AtRiskResponse {
  threshold: number;
  count: number;
  opportunities: AtRiskOpportunity[];
}

const RISK_COLORS: Record<string, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

const RISK_LABELS: Record<string, string> = {
  critical: 'Kritik',
  high: 'Yüksek',
  medium: 'Orta',
  low: 'Düşük',
};

function ScoreRing({ score }: { score: number }) {
  const color = score >= 60 ? '#22c55e' : score >= 30 ? '#f59e0b' : '#ef4444';
  const r = 28;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;

  return (
    <div className="relative h-16 w-16">
      <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} stroke="#e5e7eb" strokeWidth="5" fill="none" />
        <circle
          cx="32"
          cy="32"
          r={r}
          stroke={color}
          strokeWidth="5"
          fill="none"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-gray-900 dark:text-white">
        {score}
      </span>
    </div>
  );
}

export default function AtRiskPage() {
  const navigate = useNavigate();
  const [threshold, setThreshold] = useState(40);

  const { data, isLoading, isError } = useQuery<AtRiskResponse>({
    queryKey: ['at-risk-opps', threshold],
    queryFn: () => dealHealthApi.getAtRisk(threshold),
  });

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Riskli Fırsatlar" />
        <Skeleton variant="card" count={4} />
      </div>
    );
  }

  const opps = data?.opportunities ?? [];

  return (
    <div>
      <PageHeader
        title="Riskli Fırsatlar"
        description={`Saglik skoru ${threshold} altindaki fırsatlar`}
      >
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-500">Esik:</label>
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
          >
            <option value={30}>30</option>
            <option value={40}>40</option>
            <option value={50}>50</option>
            <option value={60}>60</option>
          </select>
        </div>
      </PageHeader>

      {/* Summary */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <div className="flex items-center gap-3 p-4">
            <div className="rounded-lg bg-red-100 p-2.5 dark:bg-red-900/30">
              <AlertTriangle size={20} className="text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{opps.length}</p>
              <p className="text-xs text-gray-500">Riskli Fırsat</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3 p-4">
            <div className="rounded-lg bg-orange-100 p-2.5 dark:bg-orange-900/30">
              <TrendingDown size={20} className="text-orange-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(opps.length * 100000, 'TRY')}
              </p>
              <p className="text-xs text-gray-500">Risk Altindaki Gelir</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3 p-4">
            <div className="rounded-lg bg-yellow-100 p-2.5 dark:bg-yellow-900/30">
              <AlertTriangle size={20} className="text-yellow-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {opps.length > 0
                  ? Math.round(opps.reduce((s, o) => s + o.score, 0) / opps.length)
                  : 0}
              </p>
              <p className="text-xs text-gray-500">Ort. Saglik Skoru</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Opportunity List */}
      {isError ? (
        <Card>
          <div className="p-8 text-center text-red-500">Veriler yuklenemedi</div>
        </Card>
      ) : opps.length === 0 ? (
        <EmptyState
          title="Riskli fırsat yok"
          description={`Saglik skoru ${threshold} altinda fırsat bulunamadi`}
        />
      ) : (
        <div className="space-y-3">
          {opps.map((opp) => (
            <Card key={opp.opportunity_id} className="overflow-hidden">
              <button
                type="button"
                onClick={() => navigate(`/opportunities/${opp.opportunity_id}`)}
                className="flex w-full items-start gap-4 p-4 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer"
              >
                <ScoreRing score={opp.score} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium text-gray-900 dark:text-white truncate">
                      {opp.title}
                    </h3>
                    <Badge
                      variant={
                        opp.risk_level === 'critical'
                          ? 'danger'
                          : opp.risk_level === 'high'
                            ? 'warning'
                            : 'default'
                      }
                      size="sm"
                    >
                      {RISK_LABELS[opp.risk_level] || opp.risk_level}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap gap-3 text-sm text-gray-500">
                    <span>Skor: {opp.score}/100</span>
                  </div>

                  {/* Indicators */}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {opp.indicators
                      .filter((ind) => ind.score < 50)
                      .map((ind) => (
                        <div
                          key={ind.name}
                          className="flex items-center gap-1.5 rounded-md bg-red-50 px-2 py-1 dark:bg-red-900/20"
                        >
                          <div
                            className={`h-1.5 w-1.5 rounded-full ${
                              RISK_COLORS[
                                ind.score < 20 ? 'critical' : ind.score < 40 ? 'high' : 'medium'
                              ]
                            }`}
                          />
                          <span className="text-xs text-red-700 dark:text-red-300">
                            {ind.label}
                          </span>
                          <span className="text-[10px] font-bold text-red-600">
                            {Math.round(ind.score)}
                          </span>
                        </div>
                      ))}
                  </div>

                  {/* Recommendations */}
                  {opp.recommendations && opp.recommendations.length > 0 && (
                    <ul className="mt-2 space-y-0.5">
                      {opp.recommendations.slice(0, 2).map((s, i) => (
                        <li key={i} className="text-xs text-gray-500">
                          • {s}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <ChevronRight size={16} className="mt-2 shrink-0 text-gray-400" />
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
