/**
 * EventAuditLogPage
 *
 * Audit finding WH-2: backend writes every domain event into
 * `domain_events`, but only the lead detail page surfaces a single
 * event type. Admins had no way to see the full firehose for
 * debugging webhook subscribers or troubleshooting "why didn't my
 * automation run?" questions.
 *
 * This stub gives an Event Audit Log surface that hits
 * `/engagement/sequences/domain-events` (already exists) with simple
 * type + limit filters. Intentionally lightweight — entity-id /
 * date-range filters and pagination are deferred to a later sprint.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RotateCw } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { sequenceV2Api } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

interface DomainEventRow {
  id: number;
  event_type: string;
  entity_type: string | null;
  entity_id: number | null;
  payload: Record<string, unknown> | null;
  actor_id: number | null;
  created_at: string | null;
}

// Mirrors backend DomainEvents constants (services/domain_events.py).
// Keep this list in sync as new event types are added — the dropdown
// is the only filter for now.
const EVENT_TYPE_OPTIONS = [
  { value: '', label: 'Tüm olaylar' },
  { value: 'sequence.step_completed', label: 'Sequence: adım tamamlandı' },
  { value: 'sequence.completed', label: 'Sequence: tamamlandı' },
  { value: 'sequence.exited', label: 'Sequence: çıkış' },
  { value: 'lead.score_changed', label: 'Lead: skor değişti' },
  { value: 'opportunity.score_changed', label: 'Fırsat: skor değişti' },
  { value: 'opportunity.stage_changed', label: 'Fırsat: stage değişti' },
  { value: 'opportunity.created', label: 'Fırsat: oluşturuldu' },
  { value: 'lead.converted', label: 'Lead: dönüştürüldü' },
  { value: 'customer.created', label: 'Müşteri: oluşturuldu' },
  { value: 'revenue_signal.created', label: 'Gelir sinyali: oluşturuldu' },
  { value: 'email.parsed', label: 'Email: ayrıştırıldı' },
  { value: 'quote.sent', label: 'Teklif: gönderildi' },
  { value: 'quote.approved', label: 'Teklif: onaylandı' },
];

const LIMIT_OPTIONS = [
  { value: '50', label: '50 kayıt' },
  { value: '100', label: '100 kayıt' },
  { value: '200', label: '200 kayıt' },
];

interface DomainEventsResponse {
  events: DomainEventRow[];
}

export default function EventAuditLogPage() {
  const [eventType, setEventType] = useState('');
  const [limit, setLimit] = useState(50);

  const { data, isLoading, isFetching, isError, refetch } = useQuery<DomainEventsResponse>({
    queryKey: ['admin', 'domain-events', eventType, limit],
    queryFn: () => sequenceV2Api.getDomainEvents(eventType || undefined, limit),
    refetchInterval: 30_000,
  });

  const events = data?.events ?? [];

  return (
    <div className="space-y-4 p-6">
      <PageHeader
        title="Olay Denetim Kaydı"
        description="Sistemin yaydığı domain olaylarını canlı izleyin (her 30 sn yenilenir)."
      >
        <Button variant="secondary" size="sm" onClick={() => refetch()} loading={isFetching}>
          <RotateCw size={14} className="mr-1.5" />
          Yenile
        </Button>
      </PageHeader>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-slate-500">Olay türü</label>
            <Select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              options={EVENT_TYPE_OPTIONS}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">Limit</label>
            <Select
              value={String(limit)}
              onChange={(e) => setLimit(Number(e.target.value))}
              options={LIMIT_OPTIONS}
            />
          </div>
        </div>
      </Card>

      <Card>
        {isError ? (
          <QueryErrorBanner variant="block" onRetry={() => refetch()} />
        ) : isLoading ? (
          <Skeleton variant="table" />
        ) : events.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-400">
            Bu filtre için olay kaydı bulunamadı.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="pb-2 pr-3 font-medium text-slate-500 dark:text-slate-400">
                    Zaman
                  </th>
                  <th className="pb-2 pr-3 font-medium text-slate-500 dark:text-slate-400">Olay</th>
                  <th className="pb-2 pr-3 font-medium text-slate-500 dark:text-slate-400">
                    Varlık
                  </th>
                  <th className="pb-2 pr-3 font-medium text-slate-500 dark:text-slate-400">
                    Aktör
                  </th>
                  <th className="pb-2 font-medium text-slate-500 dark:text-slate-400">Payload</th>
                </tr>
              </thead>
              <tbody>
                {events.map((evt) => (
                  <tr
                    key={evt.id}
                    className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                  >
                    <td className="py-2 pr-3 text-xs text-slate-500">
                      {evt.created_at ? formatDateTime(evt.created_at) : '—'}
                    </td>
                    <td className="py-2 pr-3">
                      <Badge variant="info" size="sm">
                        {evt.event_type}
                      </Badge>
                    </td>
                    <td className="py-2 pr-3 text-xs text-slate-600 dark:text-slate-300">
                      {evt.entity_type ? (
                        <span>
                          {evt.entity_type}
                          {evt.entity_id != null ? ` #${evt.entity_id}` : ''}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs text-slate-500">
                      {evt.actor_id ?? <span className="text-slate-400">sistem</span>}
                    </td>
                    <td className="py-2 max-w-xl">
                      <pre className="overflow-x-auto rounded bg-slate-50 px-2 py-1 text-[11px] text-slate-700 dark:bg-slate-900 dark:text-slate-300">
                        {evt.payload ? JSON.stringify(evt.payload, null, 0) : '∅'}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
