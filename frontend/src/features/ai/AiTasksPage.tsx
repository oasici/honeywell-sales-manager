import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { aiApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import type { AiTask } from '../../lib/types';

const STATUS_VARIANTS: Record<string, 'info' | 'warning' | 'success' | 'default'> = {
  open: 'info',
  in_progress: 'warning',
  completed: 'success',
  cancelled: 'default',
};

const PRIORITY_VARIANTS: Record<string, 'danger' | 'warning' | 'info' | 'default'> = {
  urgent: 'danger',
  high: 'warning',
  normal: 'info',
  low: 'default',
};

const INITIAL_FORM = {
  title: '',
  description: '',
  opportunity_id: '',
  due_at: '',
  priority: 'normal',
};

export default function AiTasksPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState('open');
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

  const statusLabels = useMemo(
    () => ({
      open: t('ai_tasks.status_open'),
      in_progress: t('ai_tasks.status_in_progress'),
      completed: t('ai_tasks.status_completed'),
      cancelled: t('ai_tasks.status_cancelled'),
    }),
    [t],
  );

  const priorityLabels = useMemo(
    () => ({
      urgent: t('ai_tasks.priority_urgent'),
      high: t('ai_tasks.priority_high'),
      normal: t('ai_tasks.priority_normal'),
      low: t('ai_tasks.priority_low'),
    }),
    [t],
  );

  const { data, isLoading } = useQuery<{ tasks: AiTask[] }>({
    queryKey: ['ai-tasks', filter],
    queryFn: () => aiApi.listTasks(filter),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => aiApi.createTask(payload),
    onSuccess: () => {
      toast.success(t('ai_tasks.toast_created'));
      setModalOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['ai-tasks'] });
    },
    onError: () => toast.error(t('ai_tasks.toast_create_failed')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) =>
      aiApi.updateTask(id, payload),
    onSuccess: () => {
      toast.success(t('ai_tasks.toast_updated'));
      queryClient.invalidateQueries({ queryKey: ['ai-tasks'] });
    },
    onError: () => toast.error(t('ai_tasks.toast_update_failed')),
  });

  const tasks = data?.tasks ?? [];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: Record<string, unknown> = {
      title: form.title,
      description: form.description || undefined,
      priority: form.priority,
    };
    if (form.opportunity_id) payload.opportunity_id = Number(form.opportunity_id);
    if (form.due_at) payload.due_at = form.due_at;
    createMutation.mutate(payload);
  };

  return (
    <div>
      <PageHeader title={t('ai_tasks.title')} description={t('ai_tasks.description')}>
        <Button onClick={() => setModalOpen(true)}>
          <Plus size={16} className="mr-1" /> {t('ai_tasks.new')}
        </Button>
      </PageHeader>

      {/* Filters */}
      <div className="mb-6 flex gap-2">
        {['open', 'in_progress', 'completed', 'cancelled'].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === s
                ? 'bg-honeywell-red/10 text-honeywell-red'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {statusLabels[s as keyof typeof statusLabels]}
          </button>
        ))}
      </div>

      {/* Task List */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} variant="card" />
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState
          title={t('ai_tasks.empty')}
          description={t('ai_tasks.empty_status').replace(
            '{status}',
            statusLabels[filter as keyof typeof statusLabels] ?? filter,
          )}
        />
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <Card key={task.id}>
              <div className="flex items-start justify-between gap-4 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-sm font-semibold text-gray-900 truncate">{task.title}</h3>
                    <Badge variant={PRIORITY_VARIANTS[task.priority] ?? 'default'} size="sm">
                      {priorityLabels[task.priority as keyof typeof priorityLabels] ??
                        task.priority}
                    </Badge>
                    <Badge variant={STATUS_VARIANTS[task.status] ?? 'default'} size="sm">
                      {statusLabels[task.status as keyof typeof statusLabels] ?? task.status}
                    </Badge>
                    {task.source === 'ai' && (
                      <Badge variant="info" size="sm">
                        AI
                      </Badge>
                    )}
                  </div>
                  {task.description && (
                    <p className="text-xs text-gray-500 mb-1 line-clamp-2">{task.description}</p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <span className="flex items-center gap-1">
                      <Clock size={12} /> {formatDateTime(task.created_at)}
                    </span>
                    {task.due_at && (
                      <span className="flex items-center gap-1">
                        <AlertTriangle size={12} /> {t('ai_tasks.due_short')}{' '}
                        {formatDateTime(task.due_at)}
                      </span>
                    )}
                    {task.opportunity_id && (
                      <span>
                        {t('ai_tasks.opp_ref').replace('{id}', String(task.opportunity_id))}
                      </span>
                    )}
                  </div>
                </div>
                {task.status === 'open' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      updateMutation.mutate({ id: task.id, payload: { status: 'completed' } })
                    }
                  >
                    <CheckCircle2 size={16} className="mr-1" /> {t('ai_tasks.complete')}
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={t('ai_tasks.modal_title')}
        size="md"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label={t('ai_tasks.label_title')}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
          />
          <Input
            label={t('ai_tasks.label_description')}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label={t('ai_tasks.label_opp_optional')}
              type="number"
              value={form.opportunity_id}
              onChange={(e) => setForm({ ...form, opportunity_id: e.target.value })}
            />
            <Input
              label={t('ai_tasks.label_due')}
              type="datetime-local"
              value={form.due_at}
              onChange={(e) => setForm({ ...form, due_at: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('ai_tasks.label_priority')}
            </label>
            <select
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            >
              <option value="low">{t('ai_tasks.priority_low')}</option>
              <option value="normal">{t('ai_tasks.priority_normal')}</option>
              <option value="high">{t('ai_tasks.priority_high')}</option>
              <option value="urgent">{t('ai_tasks.priority_urgent')}</option>
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              {t('common.save')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
