import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Phone, Video, FileText } from 'lucide-react';
import { activitiesApi } from '../../lib/api';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { formatDate } from '../../lib/formatters';
import QuickActivityModal from './QuickActivityModal';
import { useT } from '../../hooks/useT';
import type { ActivityLogFull } from '../../lib/types';

interface ActivityLogPanelProps {
  opportunityId: number;
}

const TYPE_ICON: Record<string, React.ReactNode> = {
  call: <Phone className="h-4 w-4 text-blue-500" />,
  meeting: <Video className="h-4 w-4 text-purple-500" />,
  note: <FileText className="h-4 w-4 text-slate-500" />,
};

const TYPE_LABELS: Record<string, string> = {
  call: 'Arama',
  meeting: 'Toplanti',
  note: 'Not',
};

const OUTCOME_LABELS: Record<string, string> = {
  baglandi: 'Baglandi',
  mesaj_birakti: 'Mesaj Birakti',
  cevap_yok: 'Cevap Yok',
  tamamlandi: 'Tamamlandi',
  ertelendi: 'Ertelendi',
  iptal: 'İptal',
};

const OUTCOME_VARIANT: Record<string, 'success' | 'warning' | 'danger' | 'default'> = {
  baglandi: 'success',
  mesaj_birakti: 'warning',
  cevap_yok: 'danger',
  tamamlandi: 'success',
  ertelendi: 'warning',
  iptal: 'danger',
};

function groupByDate(items: ActivityLogFull[]): Record<string, ActivityLogFull[]> {
  const groups: Record<string, ActivityLogFull[]> = {};
  for (const item of items) {
    const dateKey = formatDate(item.created_at);
    if (!groups[dateKey]) {
      groups[dateKey] = [];
    }
    groups[dateKey].push(item);
  }
  return groups;
}

export default function ActivityLogPanel({ opportunityId }: ActivityLogPanelProps) {
  const t = useT();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery<{ items: ActivityLogFull[] }>({
    queryKey: ['activities', opportunityId],
    queryFn: () => activitiesApi.list({ opportunity_id: opportunityId }),
    enabled: !!opportunityId,
  });

  const activities = data?.items || [];
  const grouped = groupByDate(activities);

  return (
    <>
      <Card title="Aktivite Gecmisi">
        <div className="mb-4 flex justify-end">
          <Button size="sm" onClick={() => setIsModalOpen(true)}>
            Yeni Aktivite
          </Button>
        </div>

        {isError ? (
          <QueryErrorBanner variant="block" onRetry={() => refetch()} />
        ) : isLoading ? (
          <Skeleton variant="card" count={2} />
        ) : activities.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-400">{t('common.no_activity')}</p>
        ) : (
          <div className="space-y-5">
            {Object.entries(grouped).map(([date, items]) => (
              <div key={date}>
                <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
                  {date}
                </h4>
                <div className="space-y-2">
                  {items.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-3 rounded-lg border border-slate-100 px-3 py-2.5 dark:border-slate-800"
                    >
                      <div className="mt-0.5 shrink-0">
                        {TYPE_ICON[item.activity_type] || (
                          <FileText className="h-4 w-4 text-slate-400" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                            {TYPE_LABELS[item.activity_type] || item.activity_type}
                          </span>
                          {item.duration_minutes != null && (
                            <Badge variant="default" size="sm">
                              {item.duration_minutes} dk
                            </Badge>
                          )}
                          {item.outcome && (
                            <Badge variant={OUTCOME_VARIANT[item.outcome] || 'default'} size="sm">
                              {OUTCOME_LABELS[item.outcome] || item.outcome}
                            </Badge>
                          )}
                        </div>
                        <p className="mt-0.5 text-sm text-slate-900 dark:text-white">
                          {item.summary}
                        </p>
                        {/* agenda + attendees are write-only without
                            this block — captured by QuickActivityModal
                            but never read back (audit F-11). */}
                        {item.agenda && (
                          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                            <span className="font-medium text-slate-600 dark:text-slate-300">
                              Gündem:
                            </span>{' '}
                            {item.agenda}
                          </p>
                        )}
                        {(() => {
                          if (!item.attendees_json) return null;
                          let names: string[] = [];
                          try {
                            const parsed = JSON.parse(item.attendees_json) as unknown;
                            if (Array.isArray(parsed)) {
                              names = parsed
                                .map((p) =>
                                  typeof p === 'string'
                                    ? p
                                    : typeof p === 'object' && p !== null && 'name' in p
                                      ? String((p as { name: unknown }).name)
                                      : null,
                                )
                                .filter((n): n is string => Boolean(n));
                            }
                          } catch {
                            return null;
                          }
                          if (names.length === 0) return null;
                          return (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {names.slice(0, 5).map((n, i) => (
                                <span
                                  key={i}
                                  className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                                >
                                  {n}
                                </span>
                              ))}
                              {names.length > 5 && (
                                <span className="rounded-full bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                                  +{names.length - 5}
                                </span>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <QuickActivityModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        opportunityId={opportunityId}
      />
    </>
  );
}
