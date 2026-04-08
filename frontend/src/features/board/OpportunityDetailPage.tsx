import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { opportunitiesApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatCurrency, formatDateTime } from '../../lib/formatters';
import type { Opportunity, OpportunityEvent } from '../../lib/types';

const STAGE_LABELS: Record<string, string> = {
  prospecting: 'Arastirma',
  qualified: 'Nitelenmis',
  proposal: 'Teklif',
  negotiation: 'Muzakere',
  closed_won: 'Kazanildi',
  closed_lost: 'Kaybedildi',
};

export default function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const oppId = Number(id);

  const { data: opp, isLoading } = useQuery<Opportunity>({
    queryKey: ['opportunity', oppId],
    queryFn: () => opportunitiesApi.get(oppId),
    enabled: !!oppId,
  });

  const { data: timelineData } = useQuery<{ events: OpportunityEvent[] }>({
    queryKey: ['opportunity-timeline', oppId],
    queryFn: () => opportunitiesApi.getTimeline(oppId),
    enabled: !!oppId,
  });

  if (isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!opp) {
    return <div className="py-16 text-center text-gray-500">Firsat bulunamadi</div>;
  }

  const events = timelineData?.events || [];

  return (
    <div>
      <PageHeader title={opp.title} description={STAGE_LABELS[opp.stage] || opp.stage}>
        <Button variant="secondary" onClick={() => navigate('/board')}>
          Board'a Don
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: Details */}
        <div className="lg:col-span-2 space-y-6">
          <Card title="Firsat Bilgileri">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Asama</span>
                <p className="font-semibold text-gray-900 dark:text-white">
                  {STAGE_LABELS[opp.stage] || opp.stage}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Tutar</span>
                <p className="font-semibold text-gray-900 dark:text-white">
                  {opp.amount != null ? formatCurrency(opp.amount, opp.currency) : '-'}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Kapanma Tarihi</span>
                <p className="text-gray-700 dark:text-gray-300">{opp.close_date || '-'}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Sahip</span>
                <p className="text-gray-700 dark:text-gray-300">{opp.owner?.full_name || '-'}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Musteri</span>
                <p className="text-gray-700 dark:text-gray-300">
                  {opp.customer ? `${opp.customer.name} (${opp.customer.company})` : '-'}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">Rotting</span>
                <p className={`font-semibold ${opp.rotting_days > 7 ? 'text-red-600' : 'text-gray-700 dark:text-gray-300'}`}>
                  {opp.rotting_days} gun
                </p>
              </div>
            </div>
          </Card>

          {/* Related Quotes */}
          {opp.quotes && opp.quotes.length > 0 && (
            <Card title="Iliskili Teklifler">
              <div className="space-y-2">
                {opp.quotes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/quotes/${q.id}`)}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                  >
                    <span className="font-mono text-sm font-semibold text-gray-900 dark:text-white">
                      {q.quote_number}
                    </span>
                    <div className="flex items-center gap-3">
                      <Badge variant="default" size="sm">{q.status}</Badge>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {formatCurrency(q.grand_total, opp.currency)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>

        {/* Right: Timeline */}
        <div>
          <Card title="Timeline">
            {events.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">Henuz olay yok</p>
            ) : (
              <div className="space-y-0">
                {events.map((event, idx) => (
                  <div key={event.id} className="relative flex gap-3 pb-4">
                    {/* Line */}
                    {idx < events.length - 1 && (
                      <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-gray-700" />
                    )}
                    {/* Dot */}
                    <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full bg-gray-100 flex items-center justify-center dark:bg-gray-700">
                      <div className={`h-2.5 w-2.5 rounded-full ${
                        event.event_type === 'stage_change' ? 'bg-blue-500' : 'bg-gray-400'
                      }`} />
                    </div>
                    {/* Content */}
                    <div className="min-w-0">
                      <p className="text-sm text-gray-900 dark:text-white">
                        {event.description || event.event_type}
                      </p>
                      <p className="text-[10px] text-gray-400">
                        {formatDateTime(event.occurred_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
