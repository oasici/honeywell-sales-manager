import { useState, useRef, useCallback } from 'react';

const PREFIX = 'dash_sort_';

export function useDragSort<T extends string>(key: string, defaultOrder: T[]) {
  const storageKey = PREFIX + key;

  const [order, setOrder] = useState<T[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        // Validate: same length and same items
        if (
          Array.isArray(parsed) &&
          parsed.length === defaultOrder.length &&
          defaultOrder.every((id) => parsed.includes(id))
        ) {
          return parsed;
        }
      }
    } catch { /* ignore */ }
    return defaultOrder;
  });

  const dragRef = useRef<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);

  const onDragStart = useCallback((id: string) => {
    dragRef.current = id;
  }, []);

  const onDragOver = useCallback((e: React.DragEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (dragRef.current && dragRef.current !== id) {
      setDragOverId(id);
    }
  }, []);

  const onDrop = useCallback((targetId: string) => {
    const sourceId = dragRef.current;
    dragRef.current = null;
    setDragOverId(null);

    if (!sourceId || sourceId === targetId) return;

    setOrder((prev) => {
      const next = [...prev];
      const srcIdx = next.indexOf(sourceId as T);
      const tgtIdx = next.indexOf(targetId as T);
      if (srcIdx === -1 || tgtIdx === -1) return prev;
      next.splice(srcIdx, 1);
      next.splice(tgtIdx, 0, sourceId as T);
      localStorage.setItem(storageKey, JSON.stringify(next));
      return next;
    });
  }, [storageKey]);

  const onDragEnd = useCallback(() => {
    dragRef.current = null;
    setDragOverId(null);
  }, []);

  return { order, dragOverId, onDragStart, onDragOver, onDrop, onDragEnd };
}
