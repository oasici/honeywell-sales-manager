import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { engagementApi } from '../../lib/api';
import type { EngagementScorecard } from '../../lib/types';

const WINDOW_OPTIONS = [
  { value: 7, label: '7 Gun' },
  { value: 14, label: '14 Gun' },
  { value: 30, label: '30 Gun' },
  { value: 60, label: '60 Gun' },
  { value: 90, label: '90 Gun' },
];

export default function ScorecardsPage() {
  const [window, setWindow] = useState(30);

  const { data, isLoading, isError, refetch } = useQuery<{
    window_days: number;
    scorecards: EngagementScorecard[];
  }>({
    queryKey: ['coaching-scorecards', window],
    queryFn: () => engagementApi.getCoachingScorecards(window),
  });

  const scorecards = data?.scorecards ?? [];

  const columns = [
    {
      key: 'full_name',
      header: 'Ad Soyad',
      sortable: true,
      render: (row: EngagementScorecard) => (
        <span className="text-sm font-medium text-slate-900">{row.full_name}</span>
      ),
    },
    {
      key: 'total_quotes',
      header: 'Toplam Teklif',
      sortable: true,
      render: (row: EngagementScorecard) => (
        <span className="text-sm">{row.total_quotes}</span>
      ),
    },
    {
      key: 'sent_quotes',
      header: 'Gonderilen Teklif',
      sortable: true,
      render: (row: EngagementScorecard) => (
        <span className="text-sm">{row.sent_quotes}</span>
      ),
    },
    {
      key: 'emails_assigned',
      header: 'Atanan Email',
      sortable: true,
      render: (row: EngagementScorecard) => (
        <span className="text-sm">{row.emails_assigned}</span>
      ),
    },
    {
      key: 'emails_processed',
      header: 'Islenen Email',
      sortable: true,
      render: (row: EngagementScorecard) => (
        <span className="text-sm">{row.emails_processed}</span>
      ),
    },
    {
      key: 'process_rate',
      header: 'Isleme Orani',
      sortable: true,
      render: (row: EngagementScorecard) => {
        const percentage = Math.round(row.process_rate * 100);
        const colorClass =
          percentage >= 80
            ? 'text-green-700 bg-green-100'
            : percentage >= 50
              ? 'text-yellow-700 bg-yellow-100'
              : 'text-red-700 bg-red-100';
        return (
          <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClass}`}>
            %{percentage}
          </span>
        );
      },
    },
    {
      key: 'signals_detected',
      header: 'Sinyal Sayisi',
      sortable: true,
      render: (row: EngagementScorecard) => (
        <span className="text-sm">{row.signals_detected}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Performans Kartlari" description="Satış ekibi etkinlik skorlari">
        <div className="flex items-center gap-2">
          {WINDOW_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={window === opt.value ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setWindow(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </PageHeader>

      {isError ? (
        <QueryErrorBanner variant="block" onRetry={() => refetch()} />
      ) : isLoading ? (
        <Skeleton variant="table" />
      ) : scorecards.length === 0 ? (
        <EmptyState
          title="Skor karti bulunamadi"
          description="Seçilen donem için veri yok"
          icon={<BarChart3 size={40} />}
        />
      ) : (
        <DataTable
          columns={columns}
          data={scorecards}
          loading={isLoading}
          emptyMessage="Skor karti bulunamadi"
        />
      )}
    </div>
  );
}
