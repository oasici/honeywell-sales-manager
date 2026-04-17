import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { playbookApi } from '../../lib/api';

import type { PlaybookTemplate } from '../../lib/types';

const CATEGORY_LABELS: Record<string, string> = {
  retention: 'Elde Tutma',
  growth: 'Buyume',
  pipeline: 'Pipeline',
};

const CATEGORY_COLORS: Record<string, 'info' | 'success' | 'warning'> = {
  retention: 'info',
  growth: 'success',
  pipeline: 'warning',
};

export default function PlaybookTemplatesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
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
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      navigate('/playbooks');
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  const templates: PlaybookTemplate[] = data?.items ?? [];

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
                <h3 className="font-semibold text-gray-900 dark:text-white">{template.name}</h3>

                {template.description && (
                  <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-3">
                    {template.description}
                  </p>
                )}

                {template.category && (
                  <div>
                    <Badge variant={CATEGORY_COLORS[template.category] ?? 'default'}>
                      {CATEGORY_LABELS[template.category] ?? template.category}
                    </Badge>
                  </div>
                )}

                <div className="pt-2 border-t border-gray-100 dark:border-gray-700">
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
