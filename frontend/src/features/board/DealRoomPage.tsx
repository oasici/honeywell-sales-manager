import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { dealRoomsApi } from '../../lib/api';
import { onDealRoomChanged } from '../../lib/cacheInvalidation';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import type { DealRoom } from '../../lib/types';

interface SharedItem {
  type: string;
  title: string;
  url: string;
}

interface ActionPlanItem {
  task: string;
  due_date: string;
  owner: string;
  completed: boolean;
}

function parseJsonSafe<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export default function DealRoomPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const roomId = Number(id);

  const {
    data: room,
    isLoading,
    isError,
    refetch,
  } = useQuery<DealRoom>({
    queryKey: ['deal-room', roomId],
    queryFn: () => dealRoomsApi.get(roomId),
    enabled: !!roomId,
  });

  const [sharedItems, setSharedItems] = useState<SharedItem[] | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlanItem[] | null>(null);
  const [welcomeMessage, setWelcomeMessage] = useState<string | null>(null);
  const [isLinkCopied, setIsLinkCopied] = useState(false);

  // Sync state from server data on first load
  const isInitialized = sharedItems !== null || actionPlan !== null;
  if (room && !isInitialized) {
    setSharedItems(parseJsonSafe<SharedItem[]>(room.shared_items_json, []));
    setActionPlan(parseJsonSafe<ActionPlanItem[]>(room.mutual_action_plan_json, []));
    setWelcomeMessage(room.welcome_message ?? '');
  }

  const [newItem, setNewItem] = useState<SharedItem>({ type: 'document', title: '', url: '' });
  const [newAction, setNewAction] = useState<ActionPlanItem>({
    task: '',
    due_date: '',
    owner: '',
    completed: false,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      dealRoomsApi.update(roomId, {
        shared_items_json: JSON.stringify(sharedItems),
        mutual_action_plan_json: JSON.stringify(actionPlan),
        welcome_message: welcomeMessage,
      }),
    onSuccess: () => {
      toast.success(t('deal_room.toast_saved'));
      onDealRoomChanged(queryClient, roomId);
    },
    onError: () => toast.error(t('deal_room.toast_save_failed')),
  });

  const handleCopyLink = () => {
    if (!room) return;
    const publicUrl = `${window.location.origin}/deal-rooms/public/${room.external_token}`;
    navigator.clipboard.writeText(publicUrl);
    setIsLinkCopied(true);
    toast.success(t('deal_room.copied'));
    setTimeout(() => setIsLinkCopied(false), 2000);
  };

  const handleAddItem = () => {
    if (!newItem.title || !newItem.url) return;
    setSharedItems((prev) => [...(prev ?? []), { ...newItem }]);
    setNewItem({ type: 'document', title: '', url: '' });
  };

  const handleRemoveItem = (index: number) => {
    setSharedItems((prev) => (prev ?? []).filter((_, i) => i !== index));
  };

  const handleAddAction = () => {
    if (!newAction.task) return;
    setActionPlan((prev) => [...(prev ?? []), { ...newAction }]);
    setNewAction({ task: '', due_date: '', owner: '', completed: false });
  };

  const handleToggleAction = (index: number) => {
    setActionPlan((prev) =>
      (prev ?? []).map((item, i) => (i === index ? { ...item, completed: !item.completed } : item)),
    );
  };

  const handleRemoveAction = (index: number) => {
    setActionPlan((prev) => (prev ?? []).filter((_, i) => i !== index));
  };

  if (isError) {
    return <QueryErrorBanner variant="block" onRetry={() => refetch()} />;
  }

  if (isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!room) {
    return <div className="py-16 text-center text-slate-500">{t('deal_room.not_found')}</div>;
  }

  const currentSharedItems = sharedItems ?? [];
  const currentActionPlan = actionPlan ?? [];

  return (
    <div>
      <PageHeader title={room.name} description={t('deal_room.description')}>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handleCopyLink}>
            {isLinkCopied ? t('deal_room.copied') : t('deal_room.copy_external')}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            {t('common.back')}
          </Button>
        </div>
      </PageHeader>

      {/* Last buyer activity */}
      {room.last_buyer_activity_at && (
        <div className="mb-4">
          <Badge variant="default" size="sm">
            Son alici aktivitesi: {formatDateTime(room.last_buyer_activity_at)}
          </Badge>
        </div>
      )}

      {/* Welcome Message */}
      <div className="mb-6">
        <Card title={t('deal_room.welcome')}>
          <textarea
            value={welcomeMessage ?? ''}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
            placeholder={t('deal_room.welcome_placeholder')}
          />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Shared Items */}
        <Card title={t('deal_room.shared_items')}>
          <div className="space-y-3">
            {currentSharedItems.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">
                {t('deal_room.shared_items_empty')}
              </p>
            ) : (
              currentSharedItems.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-white">
                      {item.title}
                    </p>
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline truncate block"
                    >
                      {item.url}
                    </a>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="default" size="sm">
                      {item.type}
                    </Badge>
                    <button
                      type="button"
                      onClick={() => handleRemoveItem(idx)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      {t('deal_room.remove')}
                    </button>
                  </div>
                </div>
              ))
            )}

            {/* Add item form */}
            <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <input
                  value={newItem.title}
                  onChange={(e) => setNewItem((p) => ({ ...p, title: e.target.value }))}
                  placeholder={t('deal_room.item_title')}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                />
                <input
                  value={newItem.url}
                  onChange={(e) => setNewItem((p) => ({ ...p, url: e.target.value }))}
                  placeholder={t('deal_room.item_url')}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                />
                <select
                  value={newItem.type}
                  onChange={(e) => setNewItem((p) => ({ ...p, type: e.target.value }))}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                >
                  <option value="document">{t('deal_room.type_document')}</option>
                  <option value="quote">{t('deal_room.type_quote')}</option>
                  <option value="link">{t('deal_room.type_link')}</option>
                </select>
              </div>
              <div className="mt-2 flex justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleAddItem}
                  disabled={!newItem.title || !newItem.url}
                >
                  {t('deal_room.add_item')}
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* Mutual Action Plan */}
        <Card title={t('deal_room.action_plan')}>
          <div className="space-y-3">
            {currentActionPlan.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">
                {t('deal_room.action_plan_empty')}
              </p>
            ) : (
              currentActionPlan.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800"
                >
                  <input
                    type="checkbox"
                    checked={item.completed}
                    onChange={() => handleToggleAction(idx)}
                    className="h-4 w-4 rounded border-slate-200"
                  />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-sm font-medium ${item.completed ? 'line-through text-slate-400' : 'text-slate-900 dark:text-white'}`}
                    >
                      {item.task}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      {item.due_date && (
                        <span>
                          {t('deal_room.date')}: {item.due_date}
                        </span>
                      )}
                      {item.owner && (
                        <span>
                          {t('deal_room.owner')}: {item.owner}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveAction(idx)}
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    {t('deal_room.remove')}
                  </button>
                </div>
              ))
            )}

            {/* Add action form */}
            <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <input
                  value={newAction.task}
                  onChange={(e) => setNewAction((p) => ({ ...p, task: e.target.value }))}
                  placeholder={t('deal_room.task')}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                />
                <input
                  type="date"
                  value={newAction.due_date}
                  onChange={(e) => setNewAction((p) => ({ ...p, due_date: e.target.value }))}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                />
                <input
                  value={newAction.owner}
                  onChange={(e) => setNewAction((p) => ({ ...p, owner: e.target.value }))}
                  placeholder={t('deal_room.owner')}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                />
              </div>
              <div className="mt-2 flex justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleAddAction}
                  disabled={!newAction.task}
                >
                  {t('deal_room.add_action')}
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Save */}
      <div className="mt-6 flex justify-end">
        <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
          {t('common.save')}
        </Button>
      </div>
    </div>
  );
}
