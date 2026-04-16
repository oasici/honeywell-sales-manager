import { X } from 'lucide-react';

interface BulkAction {
  key: string;
  label: string;
  variant?: 'primary' | 'danger';
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
  const isVisible = selectedCount > 0;

  return (
    <div
      className={`fixed bottom-0 left-0 right-0 z-50 transition-transform duration-300 ease-in-out ${
        isVisible ? 'translate-y-0' : 'translate-y-full'
      }`}
      role="toolbar"
      aria-label="Toplu islem araclari"
      aria-hidden={!isVisible}
    >
      <div className="bg-gray-900 shadow-2xl border-t border-gray-700">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between py-3">
            {/* Left: Selection count */}
            <span className="text-sm font-medium text-white">
              {selectedCount} kayit secili
            </span>

            {/* Center: Action buttons */}
            <div className="flex items-center gap-2">
              {actions.map((action) => (
                <button
                  key={action.key}
                  type="button"
                  onClick={() => onAction(action.key)}
                  className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    action.variant === 'danger'
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : action.variant === 'primary'
                        ? 'bg-blue-600 text-white hover:bg-blue-700'
                        : 'bg-gray-700 text-white hover:bg-gray-600'
                  }`}
                >
                  {action.label}
                </button>
              ))}
            </div>

            {/* Right: Clear button */}
            <button
              type="button"
              onClick={onClearSelection}
              className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-gray-300 hover:text-white transition-colors"
              aria-label="Secimi temizle"
            >
              <X size={16} />
              Temizle
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
