import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { playbookApi } from '../../lib/api';
import { onPlaybookChanged } from '../../lib/cacheInvalidation';

import type { PlaybookTemplate } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { translatePlaybookCategory } from '../../lib/labelTranslations';

const CATEGORY_COLORS: Record<string, 'info' | 'success' | 'warning'> = {
  retention: 'info',
  growth: 'success',
  pipeline: 'warning',
};

export default function PlaybookTemplatesPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['playbook-templates'],
    queryFn: () => playbookApi.getTemplates(),
  });

  const createFromTemplateMutation = useMutation({
    mutationFn: (template: PlaybookTemplate) =>
      playbookApi.create({
        name: template.name,
        description: template.description,
        category: template.category,
        trigger_conditions_json: template.trigger_conditions_json,
        steps_json: template.steps_json,
      }),
    onSuccess: () => {
      toast.success('Sablondan playbook oluşturuldu');
      onPlaybookChanged(queryClient);
      navigate('/playbooks');
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  const templates: PlaybookTemplate[] = data?.items ?? [];

  if (isError) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Playbook Şablonları"
          description="Hazir sablonlardan playbook olusturun"
        />
        <QueryErrorBanner variant="block" onRetry={() => refetch()} />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Playbook Şablonları"
          description="Hazir sablonlardan playbook olusturun"
        />
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Playbook Şablonları" description="Hazir sablonlardan playbook olusturun" />

      {templates.length === 0 ? (
        <Card>
          <EmptyState
            title="Henüz şablon bulunmuyor"
            description="Playbook şablonları henüz tanimlanmamis."
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((template) => (
            <Card key={template.id}>
              <div className="flex flex-col gap-3 p-4">
                <h3 className="font-semibold text-slate-900 dark:text-white">{template.name}</h3>

                {template.description && (
                  <p className="text-sm text-slate-500 dark:text-slate-400 line-clamp-3">
                    {template.description}
                  </p>
                )}

                {template.category && (
                  <div>
                    <Badge variant={CATEGORY_COLORS[template.category] ?? 'default'}>
                      {translatePlaybookCategory(template.category, t)}
                    </Badge>
                  </div>
                )}

                <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                  <Button
                    onClick={() => createFromTemplateMutation.mutate(template)}
                    loading={createFromTemplateMutation.isPending}
                  >
                    Sablondan Oluştur
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
