import { useState, useCallback } from 'react';

interface PaginationState {
  page: number;
  pageSize: number;
}

interface UsePaginationReturn extends PaginationState {
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  nextPage: () => void;
  prevPage: () => void;
  resetPage: () => void;
  offset: number;
}

export function usePagination(
  initialPage: number = 1,
  initialPageSize: number = 20,
): UsePaginationReturn {
  const [state, setState] = useState<PaginationState>({
    page: initialPage,
    pageSize: initialPageSize,
  });

  const setPage = useCallback((page: number) => {
    setState((prev) => ({ ...prev, page }));
  }, []);

  const setPageSize = useCallback((pageSize: number) => {
    setState({ page: 1, pageSize });
  }, []);

  const nextPage = useCallback(() => {
    setState((prev) => ({ ...prev, page: prev.page + 1 }));
  }, []);

  const prevPage = useCallback(() => {
    setState((prev) => ({ ...prev, page: Math.max(1, prev.page - 1) }));
  }, []);

  const resetPage = useCallback(() => {
    setState((prev) => ({ ...prev, page: 1 }));
  }, []);

  return {
    page: state.page,
    pageSize: state.pageSize,
    setPage,
    setPageSize,
    nextPage,
    prevPage,
    resetPage,
    offset: (state.page - 1) * state.pageSize,
  };
}
