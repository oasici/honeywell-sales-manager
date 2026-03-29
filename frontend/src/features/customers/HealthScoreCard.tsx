import { Card } from '../../components/ui/Card';
import type { CustomerHealthReport } from '../../lib/types';

const RISK_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  healthy: { label: 'Saglikli', color: 'text-emerald-700', bg: 'bg-emerald-100' },
  at_risk: { label: 'Risk Altinda', color: 'text-amber-700', bg: 'bg-amber-100' },
  churning: { label: 'Kayip Riski', color: 'text-red-700', bg: 'bg-red-100' },
};

function getScoreColor(score: number): string {
  if (score >= 70) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

export function HealthScoreCard({ health }: { health: CustomerHealthReport }) {
  const risk = RISK_CONFIG[health.risk_level] || RISK_CONFIG.churning;
  const scoreColor = getScoreColor(health.score);
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (health.score / 100) * circumference;

  return (
    <Card title="Musteri Saglik Skoru">
      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Score gauge */}
        <div className="flex flex-col items-center gap-2">
          <div className="relative h-28 w-28">
            <svg className="h-28 w-28 -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" strokeWidth="8" />
              <circle
                cx="50" cy="50" r="40" fill="none"
                stroke={scoreColor} strokeWidth="8" strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                className="transition-all duration-700"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-2xl font-bold" style={{ color: scoreColor }}>
                {health.score}
              </span>
            </div>
          </div>
          <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${risk.bg} ${risk.color}`}>
            {risk.label}
          </span>
        </div>

        {/* Indicators */}
        <div className="flex-1 space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
            Gostergeler
          </h4>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {health.indicators.map((ind) => (
              <div key={ind.name} className="rounded-lg bg-gray-50 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-600">{ind.label}</span>
                  <span className="text-xs font-bold" style={{ color: getScoreColor(ind.score) }}>
                    {Math.round(ind.score)}
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full rounded-full bg-gray-200">
                  <div
                    className="h-1.5 rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(100, Math.max(0, ind.score))}%`,
                      backgroundColor: getScoreColor(ind.score),
                    }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-gray-400">{ind.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Recommendations */}
        {health.recommendations.length > 0 && (
          <div className="lg:w-64 space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              Oneriler
            </h4>
            <ul className="space-y-2">
              {health.recommendations.map((rec, i) => (
                <li key={i} className="flex gap-2 text-xs text-gray-600">
                  <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
