import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, X, Briefcase, Target, StickyNote } from 'lucide-react';

interface QuickAction {
  label: string;
  icon: typeof Briefcase;
  onClick: () => void;
}

export function QuickAddFAB() {
  const [isOpen, setIsOpen] = useState(false);
  const [isNoteOpen, setIsNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState('');
  const navigate = useNavigate();
  const fabRef = useRef<HTMLDivElement>(null);

  const actions: QuickAction[] = [
    {
      label: 'Yeni Firsat',
      icon: Briefcase,
      onClick: () => {
        setIsOpen(false);
        navigate('/board?create=1');
      },
    },
    {
      label: 'Yeni Lead',
      icon: Target,
      onClick: () => {
        setIsOpen(false);
        navigate('/leads?create=1');
      },
    },
    {
      label: 'Hizli Not',
      icon: StickyNote,
      onClick: () => {
        setIsOpen(false);
        setIsNoteOpen(true);
      },
    },
  ];

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (fabRef.current && !fabRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  return (
    <>
      <div
        ref={fabRef}
        className="fixed bottom-20 right-4 z-50 block lg:hidden"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {/* Action items */}
        {isOpen && (
          <div className="mb-3 flex flex-col items-end gap-2">
            {actions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.label}
                  type="button"
                  onClick={action.onClick}
                  className="flex items-center gap-2 rounded-full bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-lg border border-gray-200 transition-all duration-200 animate-in fade-in slide-in-from-bottom-2 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-700"
                >
                  <Icon size={16} className="text-honeywell-red" />
                  {action.label}
                </button>
              );
            })}
          </div>
        )}

        {/* FAB button */}
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className="flex h-14 w-14 items-center justify-center rounded-full bg-honeywell-red text-white shadow-lg transition-transform duration-200 hover:bg-red-700 active:scale-95"
        >
          {isOpen ? <X size={24} /> : <Plus size={24} />}
        </button>
      </div>

      {/* Quick Note Modal */}
      {isNoteOpen && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 lg:hidden">
          <div className="w-full max-w-lg rounded-t-2xl bg-white p-5 shadow-2xl dark:bg-gray-900">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                Hizli Not
              </h3>
              <button
                type="button"
                onClick={() => {
                  setIsNoteOpen(false);
                  setNoteText('');
                }}
                className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                <X size={18} />
              </button>
            </div>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Notunuzu yazin..."
              rows={4}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm resize-none focus:border-honeywell-red focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              autoFocus
            />
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setIsNoteOpen(false);
                  setNoteText('');
                }}
                className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                Iptal
              </button>
              <button
                type="button"
                onClick={() => {
                  // For now, just close - could integrate with notes API
                  setIsNoteOpen(false);
                  setNoteText('');
                }}
                disabled={!noteText.trim()}
                className="rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                Kaydet
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
