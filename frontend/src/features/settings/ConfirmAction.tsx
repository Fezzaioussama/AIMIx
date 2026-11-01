import { actionButtonClass } from './actionButton';

/** What a confirmation says: its question, what follows, and its two buttons. */
export interface ConfirmCopy {
  /** The question, which also names the group: "Delete crm?". */
  question: string;
  /** What happens if they go ahead. */
  consequence: string;
  confirmLabel: string;
  keepLabel: string;
}

interface ConfirmActionProps extends ConfirmCopy {
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A second step before what cannot be undone: go ahead, or keep things as they are (focused). */
export function ConfirmAction({
  question,
  consequence,
  confirmLabel,
  keepLabel,
  busy,
  onConfirm,
  onCancel,
}: ConfirmActionProps) {
  return (
    <div
      role="group"
      aria-label={question}
      className="mt-4 rounded-lg border border-red-400/30 bg-red-500/5 p-3 text-sm"
    >
      <p className="text-slate-200">
        {question} {consequence}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          {confirmLabel}
        </button>
        <button type="button" onClick={onCancel} autoFocus className={actionButtonClass()}>
          {keepLabel}
        </button>
      </div>
    </div>
  );
}
