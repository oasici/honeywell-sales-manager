import { useState, useMemo, type ReactNode } from 'react';
import { EmptyState } from './EmptyState';
import { Button } from './Button';
import { ArrowUp, ArrowDown } from 'lucide-react';

interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyMessage?: string;
  page?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
  onRowClick?: (row: T) => void;
}

function LoadingSkeleton({ columns }: { columns: number }) {
  return (
    <>
      {[0, 1, 2].map((row) => (
        <tr key={row} className="border-b" style={{ borderColor: 'var(--border-light)' }}>
          {Array.from({ length: columns }, (_, col) => (
            <td key={col} className="px-6 py-4">
              <div className="h-3 w-full skeleton-shimmer rounded" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function DataTable<T = any>({
  columns,
  data,
  loading = false,
  emptyMessage = 'Kayit bulunamadi',
  page,
  totalPages,
  onPageChange,
  onRowClick,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  function handleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const aVal = (a as Record<string, unknown>)[sortKey];
      const bVal = (b as Record<string, unknown>)[sortKey];
      if (aVal == null || bVal == null) return 0;
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  return (
    <div className="card-modern overflow-hidden" role="table">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr
              className="border-b bg-gray-50/80 dark:bg-white/5"
              style={{ borderColor: 'var(--border)' }}
            >
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={
                    col.sortable && sortKey === col.key
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : col.sortable
                        ? 'none'
                        : undefined
                  }
                  className={`px-6 py-3 text-overline
                    ${col.sortable ? 'cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-300' : ''}`}
                  role={col.sortable ? 'button' : undefined}
                  tabIndex={col.sortable ? 0 : undefined}
                  onClick={() => col.sortable && handleSort(col.key)}
                  onKeyDown={(e) => {
                    if (col.sortable && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault();
                      handleSort(col.key);
                    }
                  }}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable && sortKey === col.key && (
                      <span>
                        {sortDir === 'asc' ? (
                          <ArrowUp size={14} className="shrink-0" />
                        ) : (
                          <ArrowDown size={14} className="shrink-0" />
                        )}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingSkeleton columns={columns.length} />
            ) : sortedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyState title={emptyMessage} />
                </td>
              </tr>
            ) : (
              sortedData.map((row, idx) => (
                <tr
                  key={idx}
                  onClick={() => onRowClick?.(row)}
                  className={`border-b last:border-b-0 transition-colors duration-150
                    hover:bg-gray-50 dark:hover:bg-white/5
                    ${onRowClick ? 'cursor-pointer' : ''}`}
                  style={{ borderColor: 'var(--border-light)' }}
                >
                  {columns.map((col) => (
                    <td key={col.key} className="px-6 py-4 text-gray-700 dark:text-gray-300">
                      {col.render
                        ? col.render(row)
                        : (((row as Record<string, unknown>)[col.key] as ReactNode) ?? '-')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {page != null && totalPages != null && totalPages > 1 && onPageChange && (
        <div
          className="flex items-center justify-between border-t px-6 py-3"
          style={{ borderColor: 'var(--border)' }}
        >
          <span className="text-caption">
            Sayfa {page} / {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              Onceki
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              Sonraki
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
