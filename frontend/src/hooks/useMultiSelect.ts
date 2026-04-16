import { useState, useCallback, useMemo } from 'react';

export function useMultiSelect<T extends { id: number }>(items: T[]) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const toggleItem = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === items.length && items.length > 0) {
        return new Set();
      }
      return new Set(items.map((item) => item.id));
    });
  }, [items]);

  const isSelected = useCallback(
    (id: number) => selectedIds.has(id),
    [selectedIds],
  );

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const isAllSelected = useMemo(
    () => items.length > 0 && selectedIds.size === items.length,
    [items.length, selectedIds.size],
  );

  const selectedCount = selectedIds.size;

  return {
    selectedIds,
    toggleItem,
    toggleAll,
    isSelected,
    clearSelection,
    isAllSelected,
    selectedCount,
  };
}
