import { useQuery } from '@tanstack/react-query';
import { analyticsApi, opsApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { formatCurrency } from '../../lib/formatters';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const FUNNEL_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#22c55e', '#ef4444', '#94a3b8'];
const STAGE_LABELS: Record<string, string> = {
  draft: 'Taslak', pending_approval: 'Onay Bekliyor', approved: 'Onaylandi',
  sent: 'Gonderildi', accepted: 'Kabul', rejected: 'Reddedildi', expired: 'Suresi Doldu',
};

export default function SalesAnalyticsPage() {
  const { data: forecast, isLoading: fLoading } = useQuery({
    queryKey: ['forecast'], queryFn: () => analyticsApi.getForecast(30),
  });
  const { data: funnel } = useQuery({
    queryKey: ['funnel'], queryFn: () => analyticsApi.getFunnel(90),
  });
  const { data: scorecards } = useQuery({
    queryKey: ['scorecards'], queryFn: () => analyticsApi.getRepScorecards(30),
  });
  const { data: sla } = useQuery({
    queryKey: ['sla'], queryFn: () => analyticsApi.getSla(30),
  });
  const { data: discounts } = useQuery({
    queryKey: ['discounts'], queryFn: () => analyticsApi.getDiscounts(90),
  });
  const { data: winLoss } = useQuery({
    queryKey: ['winLoss'], queryFn: () => analyticsApi.getWinLossReasons(90),
  });
  const { data: dataQuality } = useQuery({
    queryKey: ['dataQuality'], queryFn: analyticsApi.getDataQuality,
  });
  const { data: queues } = useQuery({
    queryKey: ['queues'], queryFn: opsApi.getQueues,
  });

  if (fLoading) return <Skeleton variant="card" count={4} />;

  return (
    <div>
      <PageHeader title="Satis Analitiği" description="Pipeline, performans ve operasyonel metrikler" />

      {/* Row 1: Forecast + Pipeline KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4 mb-6">
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Acik Pipeline</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {formatCurrency(forecast?.open_quotes_total || 0, 'TRY')}
            </p>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Forecast (30 gun)</p>
            <p className="text-2xl font-bold text-green-600">
              {formatCurrency(forecast?.forecast_total || 0, 'TRY')}
            </p>
            <p className="text-[10px] text-gray-400">
              Kazanma orani: %{((forecast?.win_rate || 0) * 100).toFixed(0)}
            </p>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">SLA Medyan Yanit</p>
            <p className={`text-2xl font-bold ${(sla?.median_first_action_minutes || 0) > 480 ? 'text-red-600' : 'text-gray-900 dark:text-white'}`}>
              {sla?.median_first_action_minutes || 0} dk
            </p>
            <p className="text-[10px] text-gray-400">{sla?.breaches_count || 0} ihlal</p>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Indirim p50 / p90</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              %{discounts?.p50_discount_rate || 0} / %{discounts?.p90_discount_rate || 0}
            </p>
          </div>
        </Card>
      </div>

      {/* Row 2: Funnel + Win/Loss */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-6">
        <Card title="Teklif Donusum Hunisi">
          {funnel?.funnel ? (
            <div className="space-y-2 p-2">
              {funnel.funnel.map((s: { stage: string; count: number; pct: number }, i: number) => (
                <div key={s.stage} className="flex items-center gap-3">
                  <span className="w-24 text-xs text-gray-600 dark:text-gray-400 truncate">
                    {STAGE_LABELS[s.stage] || s.stage}
                  </span>
                  <div className="flex-1 h-6 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${Math.max(s.pct, 2)}%`, backgroundColor: FUNNEL_COLORS[i % FUNNEL_COLORS.length] }}
                    />
                  </div>
                  <span className="w-16 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">
                    {s.count} (%{s.pct})
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">Veri yok</p>
          )}
        </Card>

        <Card title="Kazanma/Kaybetme Nedenleri">
          {winLoss?.reasons && winLoss.reasons.length > 0 ? (
            <div className="h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={winLoss.reasons} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="reason" type="category" tick={{ fontSize: 10 }} width={100} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#6366f1" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">Henuz kapanis nedeni girilmemis</p>
          )}
        </Card>
      </div>

      {/* Row 3: Rep Scorecards */}
      <Card title="Temsilci Performansi" className="mb-6">
        {scorecards?.scorecards && scorecards.scorecards.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="py-3 px-4 text-left text-xs font-semibold text-gray-500 uppercase">Temsilci</th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">Teklif</th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">Gonderilen</th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">Kazanilan</th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">Kazanma %</th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">Gelir</th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">Ort. Indirim</th>
                </tr>
              </thead>
              <tbody>
                {scorecards.scorecards.map((r: Record<string, unknown>) => (
                  <tr key={r.user_id as number} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="py-2.5 px-4 font-medium text-gray-900 dark:text-white">{r.full_name as string}</td>
                    <td className="py-2.5 px-4 text-center">{r.quote_count as number}</td>
                    <td className="py-2.5 px-4 text-center">{r.sent_count as number}</td>
                    <td className="py-2.5 px-4 text-center">{r.won_count as number}</td>
                    <td className="py-2.5 px-4 text-center">
                      <span className={`font-semibold ${(r.win_rate as number) >= 50 ? 'text-green-600' : (r.win_rate as number) >= 30 ? 'text-yellow-600' : 'text-red-600'}`}>
                        %{r.win_rate as number}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-medium">{formatCurrency(r.revenue as number, 'TRY')}</td>
                    <td className="py-2.5 px-4 text-right">{formatCurrency(r.avg_discount as number, 'TRY')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Veri yok</p>
        )}
      </Card>

      {/* Row 4: Data Quality + Ops Queues */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-6">
        <Card title="Veri Kalitesi">
          {dataQuality ? (
            <div className="space-y-4 p-2">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Musteriler</span>
                  <span className="text-sm font-bold text-gray-900 dark:text-white">
                    %{dataQuality.customers?.completeness_pct || 0}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                  <div
                    className="h-2 rounded-full bg-green-500 transition-all"
                    style={{ width: `${dataQuality.customers?.completeness_pct || 0}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-gray-400">
                  Eksik telefon: {dataQuality.customers?.missing_phone || 0} | Eksik firma: {dataQuality.customers?.missing_company || 0}
                </p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Teklifler</span>
                  <span className="text-sm font-bold text-gray-900 dark:text-white">
                    %{dataQuality.quotes?.completeness_pct || 0}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                  <div
                    className="h-2 rounded-full bg-blue-500 transition-all"
                    style={{ width: `${dataQuality.quotes?.completeness_pct || 0}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-gray-400">
                  Musterisiz: {dataQuality.quotes?.missing_customer || 0} | Kalemsiz: {dataQuality.quotes?.missing_items || 0}
                </p>
              </div>
            </div>
          ) : <Skeleton variant="card" />}
        </Card>

        <Card title="Operasyonel Kuyruklar">
          {queues ? (
            <div className="space-y-3 p-2">
              <div className="flex items-center justify-between rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 dark:border-yellow-800 dark:bg-yellow-900/20">
                <span className="text-sm text-yellow-800 dark:text-yellow-200">Inceleme Bekleyen Email</span>
                <Badge variant="warning">{queues.review_pending_count || 0}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-800 dark:bg-blue-900/20">
                <span className="text-sm text-blue-800 dark:text-blue-200">Onay Bekleyen Teklif</span>
                <Badge variant="info">{queues.approval_pending_count || 0}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-800 dark:bg-red-900/20">
                <span className="text-sm text-red-800 dark:text-red-200">Suresi Dolacak Teklifler</span>
                <Badge variant="danger">{queues.expiring_count || 0}</Badge>
              </div>
            </div>
          ) : <Skeleton variant="card" />}
        </Card>
      </div>

      {/* Row 5: Discount Outliers + SLA Breaches */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {discounts?.outliers && discounts.outliers.length > 0 && (
          <Card title={`Yuksek Indirimli Teklifler (>${discounts.threshold_pct || 25}%)`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 px-3 text-left text-xs text-gray-500">Teklif No</th>
                    <th className="py-2 px-3 text-right text-xs text-gray-500">Indirim %</th>
                    <th className="py-2 px-3 text-right text-xs text-gray-500">Toplam</th>
                  </tr>
                </thead>
                <tbody>
                  {discounts.outliers.slice(0, 10).map((o: Record<string, unknown>) => (
                    <tr key={o.id as number} className="border-b border-gray-50 dark:border-gray-800">
                      <td className="py-2 px-3 font-mono text-xs">{o.quote_number as string}</td>
                      <td className="py-2 px-3 text-right text-red-600 font-semibold">%{o.discount_rate as number}</td>
                      <td className="py-2 px-3 text-right">{formatCurrency(o.grand_total as number, 'TRY')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {sla?.breaches && sla.breaches.length > 0 && (
          <Card title="SLA Ihlalleri">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 px-3 text-left text-xs text-gray-500">Gonderen</th>
                    <th className="py-2 px-3 text-left text-xs text-gray-500">Konu</th>
                    <th className="py-2 px-3 text-right text-xs text-gray-500">Yanit (dk)</th>
                  </tr>
                </thead>
                <tbody>
                  {sla.breaches.slice(0, 10).map((b: Record<string, unknown>, i: number) => (
                    <tr key={i} className="border-b border-gray-50 dark:border-gray-800">
                      <td className="py-2 px-3 text-xs">{b.from_address as string}</td>
                      <td className="py-2 px-3 text-xs truncate max-w-[200px]">{b.subject as string}</td>
                      <td className="py-2 px-3 text-right text-red-600 font-semibold">{b.response_minutes as number}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
