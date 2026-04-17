import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { integrationsApi } from '../../lib/api';

import type { CalendarStatus, EsignStatus } from '../../lib/types';

export default function IntegrationsPage() {
  const queryClient = useQueryClient();

  const calendarQuery = useQuery<CalendarStatus>({
    queryKey: ['integrations', 'calendar'],
    queryFn: () => integrationsApi.getCalendarStatus(),
  });

  const esignQuery = useQuery<EsignStatus>({
    queryKey: ['integrations', 'esign'],
    queryFn: () => integrationsApi.getEsignStatus(),
  });

  const connectCalendarMutation = useMutation({
    mutationFn: () => integrationsApi.connectCalendar({ provider: 'google' }),
    onSuccess: () => {
      toast.success('Takvim başarıyla baglandi');
      queryClient.invalidateQueries({ queryKey: ['integrations', 'calendar'] });
    },
    onError: () => toast.error('Takvim baglanamadi'),
  });

  const syncCalendarMutation = useMutation({
    mutationFn: () => integrationsApi.syncCalendar(),
    onSuccess: () => toast.success('Takvim senkronize edildi'),
    onError: () => toast.error('Senkronizasyon başarısız'),
  });

  const connectEsignMutation = useMutation({
    mutationFn: () => integrationsApi.connectEsign({ provider: 'docusign' }),
    onSuccess: () => {
      toast.success('E-imza başarıyla baglandi');
      queryClient.invalidateQueries({ queryKey: ['integrations', 'esign'] });
    },
    onError: () => toast.error('E-imza baglanamadi'),
  });

  const calendar = calendarQuery.data;
  const esign = esignQuery.data;
  const isCalendarConnected = calendar?.connected ?? false;
  const isEsignConnected = esign?.connected ?? false;

  return (
    <div>
      <PageHeader
        title="Entegrasyonlar"
        description="Harici servis entegrasyonlarini yonetin"
      />

      <div className="grid gap-6 md:grid-cols-2">
        {/* Calendar integration */}
        <Card title="Takvim Entegrasyonu">
          {calendarQuery.isLoading && <Skeleton variant="line" count={3} />}

          {!calendarQuery.isLoading && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-gray-700">Durum:</span>
                <Badge variant={isCalendarConnected ? 'success' : 'default'}>
                  {isCalendarConnected ? 'Bagli' : 'Bagli Değil'}
                </Badge>
              </div>

              {isCalendarConnected && calendar?.provider && (
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-gray-700">Saglayici:</span>
                  <span className="text-sm text-gray-900">{calendar.provider}</span>
                </div>
              )}

              <div className="flex gap-2">
                {!isCalendarConnected ? (
                  <Button
                    onClick={() => connectCalendarMutation.mutate()}
                    loading={connectCalendarMutation.isPending}
                  >
                    Baglan
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    onClick={() => syncCalendarMutation.mutate()}
                    loading={syncCalendarMutation.isPending}
                  >
                    Senkronize Et
                  </Button>
                )}
              </div>
            </div>
          )}
        </Card>

        {/* E-Signature integration */}
        <Card title="E-Imza Entegrasyonu">
          {esignQuery.isLoading && <Skeleton variant="line" count={3} />}

          {!esignQuery.isLoading && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-gray-700">Durum:</span>
                <Badge variant={isEsignConnected ? 'success' : 'default'}>
                  {isEsignConnected ? 'Bagli' : 'Bagli Değil'}
                </Badge>
              </div>

              {isEsignConnected && esign?.provider && (
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-gray-700">Saglayici:</span>
                  <span className="text-sm text-gray-900">{esign.provider}</span>
                </div>
              )}

              <div className="flex gap-2">
                {!isEsignConnected && (
                  <Button
                    onClick={() => connectEsignMutation.mutate()}
                    loading={connectEsignMutation.isPending}
                  >
                    Baglan
                  </Button>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
