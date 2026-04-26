import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, X, Briefcase, Target, StickyNote } from 'lucide-react';
import { Button } from '../ui/Button';

/**
 * QuickAddFAB — mobile-only floating action menu.
 *
 * Visual:
 *   - Trigger: 56×56 brand-red circle with shadow-xl. Rotates the icon
 *     45° when open (Plus → X) so the affordance feels animated rather
 *     than swapping graphics.
 *   - Action chips: white pills with slate-200 ring + shadow-lg, brand
 *     icon medallion. Stack from the bottom up with staggered slide-in.
 *   - Quick-Note bottom sheet: rounded-t-2xl on a slate-900/60 backdrop.
 *
 * Mobile-only: hidden under lg because desktop has dedicated CTAs in
 * page headers; the FAB is meant to keep a single-tap entry point on
 * the small viewport.
 */
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
      label: 'Yeni Fırsat',
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
      label: 'Hızlı Not',
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

  // Close note sheet on Escape (matches modal interaction patterns)
  useEffect(() => {
    if (!isNoteOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsNoteOpen(false);
        setNoteText('');
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isNoteOpen]);

  return (
    <>
      <div
        ref={fabRef}
        className="fixed bottom-20 right-4 z-50 block lg:hidden"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {/* Action chips — stack from the FAB upward when open. Each chip is
            a tap target with an icon medallion + label so the affordance is
            unambiguous on a small screen. */}
        {isOpen && (
          <div className="mb-3 flex flex-col items-end gap-2">
            {actions.map((action, idx) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.label}
                  type="button"
                  onClick={action.onClick}
                  className="flex items-center gap-2.5 rounded-full border border-slate-200 bg-white py-2 pl-2 pr-4 text-[13px] font-medium text-slate-800 shadow-(--shadow-lg) transition-all duration-200 active:scale-[0.97] dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
                  style={{ animationDelay: `${idx * 40}ms` }}
                >
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                    <Icon size={14} />
                  </span>
                  {action.label}
                </button>
              );
            })}
          </div>
        )}

        {/* FAB trigger */}
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          aria-label={isOpen ? 'Hızlı eylemleri kapat' : 'Hızlı eylemleri aç'}
          aria-expanded={isOpen}
          className="flex h-14 w-14 items-center justify-center rounded-full bg-honeywell-red text-white shadow-(--shadow-xl) ring-1 ring-honeywell-red/40 transition-all duration-200 hover:bg-honeywell-dark active:scale-[0.96] focus:outline-none focus:ring-[5px] focus:ring-honeywell-red/25"
        >
          <span
            className={[
              'inline-block transition-transform duration-200',
              isOpen ? 'rotate-45' : 'rotate-0',
            ].join(' ')}
          >
            <Plus size={22} strokeWidth={2.25} />
          </span>
        </button>
      </div>

      {/* Quick-Note bottom sheet */}
      {isNoteOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-900/60 backdrop-blur-[2px] lg:hidden"
          onClick={() => {
            setIsNoteOpen(false);
            setNoteText('');
          }}
        >
          <div
            className="w-full max-w-lg overflow-hidden rounded-t-2xl border-t border-slate-200 bg-white shadow-(--shadow-xl) dark:border-slate-800 dark:bg-slate-900"
            style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800">
              <div className="flex items-center gap-2.5">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                  <StickyNote size={14} />
                </span>
                <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">
                  Hızlı Not
                </h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsNoteOpen(false);
                  setNoteText('');
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label="Kapat"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-4 px-5 py-4">
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Notunuzu yazın..."
                rows={4}
                className="w-full resize-none rounded-[12px] border border-slate-200 bg-white px-3.5 py-2.5 text-[14px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="md"
                  onClick={() => {
                    setIsNoteOpen(false);
                    setNoteText('');
                  }}
                >
                  İptal
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  disabled={!noteText.trim()}
                  onClick={() => {
                    // TODO: integrate with notes API once exposed.
                    setIsNoteOpen(false);
                    setNoteText('');
                  }}
                >
                  Kaydet
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
