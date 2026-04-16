import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { dealRoomsApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatDateTime } from '../../lib/formatters';
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
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const roomId = Number(id);

  const { data: room, isLoading } = useQuery<DealRoom>({
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
      toast.success('Deal room kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['deal-room', roomId] });
    },
    onError: () => toast.error('Kaydetme basarisiz'),
  });

  const handleCopyLink = () => {
    if (!room) return;
    const publicUrl = `${window.location.origin}/deal-rooms/public/${room.external_token}`;
    navigator.clipboard.writeText(publicUrl);
    setIsLinkCopied(true);
    toast.success('Baglanti kopyalandi');
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

  if (isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!room) {
    return <div className="py-16 text-center text-gray-500">Deal room bulunamadi</div>;
  }

  const currentSharedItems = sharedItems ?? [];
  const currentActionPlan = actionPlan ?? [];

  return (
    <div>
      <PageHeader title={room.name} description="Deal Room">
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handleCopyLink}>
            {isLinkCopied ? 'Kopyalandi' : 'Harici Baglanti Kopyala'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            Geri Don
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
        <Card title="Karsilama Mesaji">
          <textarea
            value={welcomeMessage ?? ''}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
            placeholder="Aliciya gosterilecek karsilama mesaji..."
          />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Shared Items */}
        <Card title="Paylasilan Ogeler">
          <div className="space-y-3">
            {currentSharedItems.length === 0 ? (
              <p className="py-4 text-center text-sm text-gray-400">Henuz oge eklenmemis</p>
            ) : (
              currentSharedItems.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-700"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
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
                      Kaldir
                    </button>
                  </div>
                </div>
              ))
            )}

            {/* Add item form */}
            <div className="border-t border-gray-100 pt-3 dark:border-gray-700">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <input
                  value={newItem.title}
                  onChange={(e) => setNewItem((p) => ({ ...p, title: e.target.value }))}
                  placeholder="Baslik"
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />
                <input
                  value={newItem.url}
                  onChange={(e) => setNewItem((p) => ({ ...p, url: e.target.value }))}
                  placeholder="URL"
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />
                <select
                  value={newItem.type}
                  onChange={(e) => setNewItem((p) => ({ ...p, type: e.target.value }))}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                >
                  <option value="document">Dokuman</option>
                  <option value="quote">Teklif</option>
                  <option value="link">Baglanti</option>
                </select>
              </div>
              <div className="mt-2 flex justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleAddItem}
                  disabled={!newItem.title || !newItem.url}
                >
                  Oge Ekle
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* Mutual Action Plan */}
        <Card title="Karsilikli Aksiyon Plani">
          <div className="space-y-3">
            {currentActionPlan.length === 0 ? (
              <p className="py-4 text-center text-sm text-gray-400">Henuz madde eklenmemis</p>
            ) : (
              currentActionPlan.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3 rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-700"
                >
                  <input
                    type="checkbox"
                    checked={item.completed}
                    onChange={() => handleToggleAction(idx)}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-sm font-medium ${item.completed ? 'line-through text-gray-400' : 'text-gray-900 dark:text-white'}`}
                    >
                      {item.task}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      {item.due_date && <span>Tarih: {item.due_date}</span>}
                      {item.owner && <span>Sorumlu: {item.owner}</span>}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveAction(idx)}
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    Kaldir
                  </button>
                </div>
              ))
            )}

            {/* Add action form */}
            <div className="border-t border-gray-100 pt-3 dark:border-gray-700">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <input
                  value={newAction.task}
                  onChange={(e) => setNewAction((p) => ({ ...p, task: e.target.value }))}
                  placeholder="Gorev"
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />
                <input
                  type="date"
                  value={newAction.due_date}
                  onChange={(e) => setNewAction((p) => ({ ...p, due_date: e.target.value }))}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />
                <input
                  value={newAction.owner}
                  onChange={(e) => setNewAction((p) => ({ ...p, owner: e.target.value }))}
                  placeholder="Sorumlu"
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                />
              </div>
              <div className="mt-2 flex justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleAddAction}
                  disabled={!newAction.task}
                >
                  Madde Ekle
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Save */}
      <div className="mt-6 flex justify-end">
        <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
          Kaydet
        </Button>
      </div>
    </div>
  );
}
