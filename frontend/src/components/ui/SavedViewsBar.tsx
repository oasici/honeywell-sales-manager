import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bookmark, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from './Button';
import { Modal } from './Modal';
import { Input } from './Input';
import { savedViewsApi } from '../../lib/api';

/**
 * S-E — Saved views universal.
 * Drop-in component for any list/board page. Persists the current filter
 * payload as a named view scoped to the route.
 *
 * Usage:
 *   <SavedViewsBar
 *     route="/leads"
 *     queryJson={JSON.stringify(currentFilters)}
 *     onApply={(saved) => applyFilters(JSON.parse(saved.query_json))}
 *   />
 */
interface SavedViewsBarProps {
  /** Used to namespace views per page. */
  route: string;
  /** Current filter payload as JSON string. */
  queryJson: string;
  /** Called when the user picks one of their saved views. */
  onApply: (view: { id: number; name: string; query_json: string }) => void;
}

export function SavedViewsBar({ route, queryJson, onApply }: SavedViewsBarProps) {
  const qc = useQueryClient();
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [name, setName] = useState('');

  const viewsQuery = useQuery({
    queryKey: ['saved-views', route],
    queryFn: () => savedViewsApi.list(),
    staleTime: 60_000,
  });

  const createMutation = useMutation({
    mutationFn: () => savedViewsApi.create({ name, route, query_json: queryJson }),
    onSuccess: () => {
      toast.success('Görünüm kaydedildi');
      setShowSaveModal(false);
      setName('');
      qc.invalidateQueries({ queryKey: ['saved-views', route] });
    },
    onError: () => toast.error('Görünüm kaydedilemedi'),
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => savedViewsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['saved-views', route] });
    },
  });

  const myViews = (viewsQuery.data?.views ?? []).filter((v) => v.route === route);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Button variant="tertiary" size="sm" onClick={() => setShowSaveModal(true)}>
        <Bookmark className="mr-1 h-3 w-3" />
        Görünümü kaydet
      </Button>

      {myViews.map((v) => (
        <span
          key={v.id}
          className="group inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-caption text-slate-700 hover:bg-slate-200"
        >
          <button onClick={() => onApply(v)}>{v.name}</button>
          <button
            className="opacity-0 transition group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation();
              removeMutation.mutate(v.id);
            }}
            aria-label={`${v.name} sil`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}

      <Modal isOpen={showSaveModal} onClose={() => setShowSaveModal(false)} title="Görünümü kaydet">
        <div className="space-y-3">
          <Input
            label="İsim"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="örn. Yüksek değerli açık fırsatlar"
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button variant="tertiary" size="sm" onClick={() => setShowSaveModal(false)}>
              İptal
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => createMutation.mutate()}
              disabled={!name.trim() || createMutation.isPending}
            >
              Kaydet
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default SavedViewsBar;
