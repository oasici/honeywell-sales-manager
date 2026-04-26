import type { ReactNode } from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import { Modal } from './Modal';
import { Button } from './Button';

/**
 * ConfirmDialog — destructive-action confirmation built on top of Modal.
 *
 * Visual:
 *   - Tone-tinted icon medallion (danger=red / primary=brand) sits left of
 *     the body so the user reads "stop and think" before the message itself.
 *   - Footer uses Modal's footer slot so the action row is pinned to the
 *     bottom even when long messages cause the body to scroll.
 *   - Confirm button defaults to `danger` because that is the typical use
 *     case (delete/archive/revoke); pass `confirmVariant="primary"` for
 *     non-destructive confirmations (publish/approve/send).
 */
interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: 'primary' | 'danger';
  isLoading?: boolean;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Onayla',
  cancelLabel = 'İptal',
  confirmVariant = 'danger',
  isLoading,
}: ConfirmDialogProps) {
  const isDanger = confirmVariant === 'danger';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm} loading={isLoading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex items-start gap-3.5">
        <span
          aria-hidden
          className={[
            'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] ring-1 ring-inset',
            isDanger
              ? 'bg-red-50 text-red-600 ring-red-100 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-900/40'
              : 'bg-honeywell-red/8 text-honeywell-red ring-honeywell-red/15',
          ].join(' ')}
        >
          {isDanger ? <AlertTriangle size={18} /> : <Info size={18} />}
        </span>
        <div className="min-w-0 flex-1 text-[14px] leading-6 text-slate-700 dark:text-slate-300">
          {message}
        </div>
      </div>
    </Modal>
  );
}
