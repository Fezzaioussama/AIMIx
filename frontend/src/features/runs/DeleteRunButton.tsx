import { useState } from 'react';

const BUTTON =
  'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:opacity-50';

interface DeleteRunButtonProps {
  onDelete: () => void;
  /** The deletion is in flight. */
  busy?: boolean;
}

/** "Delete", then an inline "Delete this run?" with Keep focused, so it takes two clicks. */
export function DeleteRunButton({ onDelete, busy = false }: DeleteRunButtonProps) {
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className={`${BUTTON} border-white/15 text-slate-200 hover:bg-white/10`}
      >
        Delete
      </button>
    );
  }
  return (
    <span role="group" aria-label="Confirm delete" className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-slate-200">Delete this run for good?</span>
      <button
        type="button"
        onClick={onDelete}
        disabled={busy}
        className={`${BUTTON} border-red-400/50 bg-red-500/15 text-red-100 hover:bg-red-500/25`}
      >
        {busy ? 'Deleting…' : 'Yes, delete'}
      </button>
      <button
        type="button"
        // The safe choice takes the focus, so Enter never deletes by accident.
        autoFocus
        onClick={() => setConfirming(false)}
        className={`${BUTTON} border-white/15 text-slate-200 hover:bg-white/10`}
      >
        Keep
      </button>
    </span>
  );
}
