import { useCallback, useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

type ModalSize = 'sm' | 'md' | 'lg' | 'xl';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  /** Optional subtitle shown under the title (e.g. context such as "3 öğe seçildi"). */
  description?: string;
  children: ReactNode;
  size?: ModalSize;
  /** Optional footer slot — typically Cancel + primary action buttons. */
  footer?: ReactNode;
}

const sizeClasses: Record<ModalSize, string> = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  size = 'md',
  footer,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Stable close callback that never changes identity
  const stableClose = useCallback(() => onCloseRef.current(), []);

  useEffect(() => {
    if (!isOpen) return;

    // Save previously focused element
    previousFocusRef.current = document.activeElement as HTMLElement;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onCloseRef.current();
        return;
      }

      // Focus trap
      if (e.key === 'Tab' && panelRef.current) {
        const focusable = panelRef.current.querySelectorAll<HTMLElement>(
          'input, select, textarea, button, [href], [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) return;

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';

    // Focus first input on open (not button/close)
    requestAnimationFrame(() => {
      const firstInput = panelRef.current?.querySelector<HTMLElement>('input, select, textarea');
      if (firstInput) {
        firstInput.focus();
      }
    });

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      previousFocusRef.current?.focus();
    };
  }, [isOpen]); // Only re-run when isOpen changes, NOT on onClose identity change

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      aria-modal="true"
      role="dialog"
      aria-labelledby="modal-title"
    >
      {/* Backdrop — slate-tinted, slight blur. The tint reads softer than pure
          black/50 against light surfaces and matches the rest of the system. */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-[3px] animate-fade-in"
        onClick={stableClose}
        aria-hidden="true"
      />

      {/* Modal panel — 16px radius (same family as Card), shadow-xl token,
          slate-200 border. Footer is its own border-top section so the body
          area can scroll without losing the action row. */}
      <div
        ref={panelRef}
        className={`relative z-10 mx-4 w-full ${sizeClasses[size]}
          flex max-h-[85vh] flex-col overflow-hidden
          rounded-2xl border border-slate-200 bg-white
          shadow-(--shadow-xl)
          dark:border-slate-800 dark:bg-slate-900
          animate-slide-up`}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5 dark:border-slate-800">
          <div className="min-w-0 flex-1 pr-4">
            <h2 id="modal-title" className="text-heading-3 text-slate-900 dark:text-white">
              {title}
            </h2>
            {description && (
              <p className="mt-1 text-[13px] leading-5 text-slate-500 dark:text-slate-400">
                {description}
              </p>
            )}
          </div>
          <button
            onClick={stableClose}
            className="-mr-1 -mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label="Kapat"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>

        {/* Footer (optional) */}
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/40">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
