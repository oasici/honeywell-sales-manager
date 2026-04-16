import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Phone, Video, FileText } from 'lucide-react';
import { activitiesApi } from '../../lib/api';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatDate } from '../../lib/formatters';
import QuickActivityModal from './QuickActivityModal';
import type { ActivityLogFull } from '../../lib/types';

interface ActivityLogPanelProps {
  opportunityId: number;
}

const TYPE_ICON: Record<string, React.ReactNode> = {
  call: <Phone className="h-4 w-4 text-blue-500" />,
  meeting: <Video className="h-4 w-4 text-purple-500" />,
  note: <FileText className="h-4 w-4 text-gray-500" />,
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
  iptal: 'Iptal',
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
  const [isModalOpen, setIsModalOpen] = useState(false);

  const { data, isLoading } = useQuery<{ items: ActivityLogFull[] }>({
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

        {isLoading ? (
          <Skeleton variant="card" count={2} />
        ) : activities.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-400">
            Henuz aktivite kaydedilmemis
          </p>
        ) : (
          <div className="space-y-5">
            {Object.entries(grouped).map(([date, items]) => (
              <div key={date}>
                <h4 className="mb-2 text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                  {date}
                </h4>
                <div className="space-y-2">
                  {items.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-3 rounded-lg border border-gray-100 px-3 py-2.5 dark:border-gray-700"
                    >
                      <div className="mt-0.5 shrink-0">
                        {TYPE_ICON[item.activity_type] || <FileText className="h-4 w-4 text-gray-400" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                            {TYPE_LABELS[item.activity_type] || item.activity_type}
                          </span>
                          {item.duration_minutes != null && (
                            <Badge variant="default" size="sm">
                              {item.duration_minutes} dk
                            </Badge>
                          )}
                          {item.outcome && (
                            <Badge
                              variant={OUTCOME_VARIANT[item.outcome] || 'default'}
                              size="sm"
                            >
                              {OUTCOME_LABELS[item.outcome] || item.outcome}
                            </Badge>
                          )}
                        </div>
                        <p className="mt-0.5 text-sm text-gray-900 dark:text-white">
                          {item.summary}
                        </p>
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
