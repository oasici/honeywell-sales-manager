import { X } from 'lucide-react';
import { useT } from '../../hooks/useT';
import { Button } from './Button';

/**
 * BulkActionBar — floating action toolbar shown when one or more rows are
 * selected in a list/table view.
 *
 * Visual:
 *   - Floats above the bottom edge with a 16px gap (instead of edge-to-edge)
 *     so it reads as a contextual command palette rather than chrome.
 *   - Slate-950 surface with a subtle white-tinted ring + xl shadow — sits
 *     on top of any background without competing with the active page.
 *   - Selected count gets a brand-tinted pill so the "stateful" affordance
 *     is unmistakable; the rest of the bar stays calm.
 *   - Action buttons use the Button primitive for full focus/keyboard parity.
 */
interface BulkAction {
  key: string;
  label: string;
  variant?: 'primary' | 'danger' | 'secondary';
}

interface BulkActionBarProps {
  selectedCount: number;
  actions: BulkAction[];
  onAction: (key: string) => void;
  onClearSelection: () => void;
}

export function BulkActionBar({
  selectedCount,
  actions,
  onAction,
  onClearSelection,
}: BulkActionBarProps) {
  const t = useT();
  const isVisible = selectedCount > 0;

  return (
    <div
      className={[
        'pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center px-4 pb-4 pt-2 transition-transform duration-300 ease-out',
        // Bottom inset is honored by the 16px pb-4; on lg we lift another 4px
        // to clear the FAB. On mobile we sit above the bottom nav (h-16-ish).
        'lg:pb-6',
        isVisible ? 'translate-y-0' : 'translate-y-[120%]',
      ].join(' ')}
      role="toolbar"
      aria-label={t('bulk.aria_toolbar')}
      aria-hidden={!isVisible}
    >
      <div className="pointer-events-auto flex w-full max-w-3xl items-center gap-3 rounded-2xl bg-slate-950 px-3 py-2 shadow-(--shadow-xl) ring-1 ring-white/10 sm:px-4">
        {/* Selection count pill */}
        <span className="inline-flex items-center gap-2 rounded-full bg-honeywell-red/15 px-3 py-1 text-[12px] font-semibold text-white ring-1 ring-honeywell-red/40">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-honeywell-red" />
          {t('bulk.selected').replace('{count}', String(selectedCount))}
        </span>

        {/* Spacer pushes actions + clear to the right */}
        <span className="flex-1" />

        {/* Actions */}
        <div className="flex items-center gap-1.5">
          {actions.map((action) => (
            <Button
              key={action.key}
              variant={action.variant ?? 'secondary'}
              size="sm"
              onClick={() => onAction(action.key)}
            >
              {action.label}
            </Button>
          ))}
        </div>

        {/* Divider + clear */}
        <span className="hidden h-6 w-px bg-white/10 sm:inline-block" aria-hidden />
        <button
          type="button"
          onClick={onClearSelection}
          className="inline-flex h-8 items-center gap-1 rounded-[10px] px-2.5 text-[12px] font-medium text-slate-300 transition-colors hover:bg-white/8 hover:text-white focus:outline-none focus:ring-[3px] focus:ring-white/20"
          aria-label={t('bulk.clear_aria')}
        >
          <X size={14} />
          <span className="hidden sm:inline">{t('bulk.clear')}</span>
        </button>
      </div>
    </div>
  );
}
