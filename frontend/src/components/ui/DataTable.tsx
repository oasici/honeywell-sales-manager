import { useState, useMemo, type ReactNode } from 'react';
import { EmptyState } from './EmptyState';
import { Button } from './Button';
import { ArrowUp, ArrowDown } from 'lucide-react';
import { useT } from '../../hooks/useT';

/**
 * DataTable — generic list/table primitive.
 *
 * Visual upgrades (PR-design Phase 2):
 *   - Header row: bg-slate-50/60, text-overline (uppercase 11/600/0.06em),
 *     slate-100 bottom border. Stripe-style "calm" header that doesn't fight
 *     the data below.
 *   - Body rows: 14/22 slate-700; 12px vertical padding (was 16) for higher
 *     density without feeling cramped; slate-50 hover; numeric columns get
 *     tabular-nums font-feature for clean column alignment.
 *   - Loading skeleton stays inline (3 shimmer rows) so layout doesn't jump.
 *   - Empty state inherits the new EmptyState component so the affordance is
 *     consistent across the app.
 *   - Pagination footer uses the new tertiary Button variant (lighter weight).
 *
 * New props:
 *   - columns[].align: 'left' | 'right' | 'center' — typography aligns naturally
 *     for currency/number columns
 *   - columns[].width: optional CSS width to lock column sizing
 *   - density: 'comfortable' | 'compact' — compact halves the row padding
 *     for power-user list views
 */

interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  width?: string;
  /** Apply tabular-nums for clean numeric alignment. */
  numeric?: boolean;
  /**
   * R7-RESP-2 — hide the column on viewports below this Tailwind
   * breakpoint. Mirrors the `hidden sm:table-cell` pattern CLAUDE.md
   * mandates for mobile responsiveness on tables. Pre-fix the
   * primitive had no built-in mechanism, so every consumer that
   * needed responsive table layout hand-rolled their own `<table>`.
   */
  hideOn?: 'sm' | 'md' | 'lg';
}

const HIDE_CLASS: Record<NonNullable<Column<unknown>['hideOn']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
};

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyMessage?: string;
  page?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
  onRowClick?: (row: T) => void;
  density?: 'comfortable' | 'compact';
}

const ALIGN_CLASS: Record<NonNullable<Column<unknown>['align']>, string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

function LoadingSkeleton({ columns, rowPadY }: { columns: number; rowPadY: string }) {
  return (
    <>
      {[0, 1, 2, 3, 4].map((row) => (
        <tr key={row} className="border-b border-slate-100 dark:border-slate-800/60">
          {Array.from({ length: columns }, (_, col) => (
            <td key={col} className={`px-5 ${rowPadY}`}>
              <div className="h-3 w-full max-w-[180px] skeleton-shimmer rounded-md" />
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
  emptyMessage,
  page,
  totalPages,
  onPageChange,
  onRowClick,
  density = 'comfortable',
}: DataTableProps<T>) {
  const t = useT();
  const resolvedEmpty = emptyMessage ?? t('table.empty');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const rowPadY = density === 'compact' ? 'py-2.5' : 'py-3.5';

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
            <tr className="border-b border-slate-100 bg-slate-50/60 dark:border-slate-800 dark:bg-white/2">
              {columns.map((col) => {
                const align = col.align ?? (col.numeric ? 'right' : 'left');
                return (
                  <th
                    key={col.key}
                    scope="col"
                    style={col.width ? { width: col.width } : undefined}
                    aria-sort={
                      col.sortable && sortKey === col.key
                        ? sortDir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : col.sortable
                          ? 'none'
                          : undefined
                    }
                    className={[
                      'px-5 py-3 text-overline text-slate-500',
                      ALIGN_CLASS[align],
                      col.hideOn ? HIDE_CLASS[col.hideOn] : '',
                      col.sortable
                        ? 'cursor-pointer select-none hover:text-slate-700 dark:hover:text-slate-300'
                        : '',
                    ].join(' ')}
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
                    <span
                      className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}
                    >
                      {col.header}
                      {col.sortable && sortKey === col.key && (
                        <span className="text-slate-400">
                          {sortDir === 'asc' ? (
                            <ArrowUp size={12} className="shrink-0" />
                          ) : (
                            <ArrowDown size={12} className="shrink-0" />
                          )}
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingSkeleton columns={columns.length} rowPadY={rowPadY} />
            ) : sortedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyState title={resolvedEmpty} variant="compact" />
                </td>
              </tr>
            ) : (
              sortedData.map((row, idx) => (
                <tr
                  key={idx}
                  onClick={() => onRowClick?.(row)}
                  className={[
                    'border-b border-slate-100 last:border-b-0 transition-colors duration-150',
                    'hover:bg-slate-50 dark:border-slate-800/60 dark:hover:bg-white/3',
                    onRowClick ? 'cursor-pointer' : '',
                  ].join(' ')}
                >
                  {columns.map((col) => {
                    const align = col.align ?? (col.numeric ? 'right' : 'left');
                    return (
                      <td
                        key={col.key}
                        className={[
                          `px-5 ${rowPadY} text-slate-700 dark:text-slate-300`,
                          ALIGN_CLASS[align],
                          col.hideOn ? HIDE_CLASS[col.hideOn] : '',
                          col.numeric ? 'tabular-nums' : '',
                        ].join(' ')}
                      >
                        {col.render
                          ? col.render(row)
                          : (((row as Record<string, unknown>)[col.key] as ReactNode) ?? '–')}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      {page != null && totalPages != null && totalPages > 1 && onPageChange && (
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/40 px-5 py-3 dark:border-slate-800 dark:bg-white/2">
          <span className="text-caption text-slate-500">
            {t('table.page_of')
              .replace('{page}', String(page))
              .replace('{totalPages}', String(totalPages))}
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="tertiary"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              {t('table.prev')}
            </Button>
            <Button
              variant="tertiary"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              {t('table.next')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
