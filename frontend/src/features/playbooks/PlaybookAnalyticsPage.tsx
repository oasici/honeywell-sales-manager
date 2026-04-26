import { useQuery } from '@tanstack/react-query';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';

import { playbookApi } from '../../lib/api';

import type { PlaybookAnalytics } from '../../lib/types';

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <div className="p-4 text-center">
        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</p>
        <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
      </div>
    </Card>
  );
}

function WinRateCard({
  label,
  rate,
  bgClass,
}: {
  label: string;
  rate: number;
  bgClass: string;
}) {
  const percentage = `${(rate * 100).toFixed(1)}%`;
  return (
    <div className={`flex-1 rounded-xl p-6 ${bgClass}`}>
      <p className="text-sm font-medium opacity-80">{label}</p>
      <p className="mt-1 text-3xl font-bold">{percentage}</p>
    </div>
  );
}

export default function PlaybookAnalyticsPage() {
  const { data, isLoading } = useQuery<PlaybookAnalytics>({
    queryKey: ['playbook-analytics'],
    queryFn: () => playbookApi.getAnalytics(),
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Playbook Analitikleri" description="Playbook performans istatistikleri" />
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Playbook Analitikleri"
        description="Playbook performans istatistikleri"
      />

      {/* KPI cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard label="Toplam Yürütme" value={data.total_executions} />
        <KpiCard label="Tamamlanan" value={data.total_completed} />
        <KpiCard label="Ort. Tamamlanma (Gun)" value={data.avg_completion_days.toFixed(1)} />
      </div>

      {/* Win rate comparison */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white">
          Kazanma Orani Karsilastirmasi
        </h2>
        <div className="flex gap-4">
          <WinRateCard
            label="Playbook ile"
            rate={data.win_rate_with_playbook}
            bgClass="bg-green-50 text-green-900 dark:bg-green-900/30 dark:text-green-300"
          />
          <WinRateCard
            label="Playbook'suz"
            rate={data.win_rate_without_playbook}
            bgClass="bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          />
        </div>
      </div>

      {/* Per-playbook table */}
      <Card>
        <div className="p-4">
          <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white">
            Playbook Bazinda Performans
          </h2>
          {data.per_playbook.length === 0 ? (
            <p className="text-sm text-slate-500">Veri bulunmuyor.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800">
                    <th className="pb-2 font-medium text-slate-500">Playbook</th>
                    <th className="pb-2 font-medium text-slate-500">Yürütme</th>
                    <th className="pb-2 font-medium text-slate-500">Tamamlanan</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_playbook.map((item) => (
                    <tr
                      key={item.playbook_id}
                      className="border-b border-slate-100 dark:border-slate-800 last:border-b-0"
                    >
                      <td className="py-2 text-slate-900 dark:text-white">{item.name}</td>
                      <td className="py-2 text-slate-700 dark:text-slate-300">{item.executions}</td>
                      <td className="py-2 text-slate-700 dark:text-slate-300">{item.completed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {/* Most triggered */}
      <Card>
        <div className="p-4">
          <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white">
            En Çok Tetiklenenler
          </h2>
          {data.most_triggered.length === 0 ? (
            <p className="text-sm text-slate-500">Veri bulunmuyor.</p>
          ) : (
            <ul className="space-y-2">
              {data.most_triggered.map((item) => (
                <li
                  key={item.playbook_id}
                  className="flex items-center justify-between rounded-lg border border-slate-100 px-4 py-2 dark:border-slate-800"
                >
                  <span className="text-sm font-medium text-slate-900 dark:text-white">
                    {item.name}
                  </span>
                  <span className="text-sm font-bold text-slate-600 dark:text-slate-400">
                    {item.count} kez
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}
