import { useState } from 'react';

import { RUN_BUTTON } from './runButtons';

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
      <button type="button" onClick={() => setConfirming(true)} className={RUN_BUTTON.neutral}>
        Delete
      </button>
    );
  }
  return (
    <span role="group" aria-label="Confirm delete" className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-slate-200">Delete this run for good?</span>
      <button type="button" onClick={onDelete} disabled={busy} className={RUN_BUTTON.danger}>
        {busy ? 'Deleting…' : 'Yes, delete'}
      </button>
      <button
        type="button"
        // The safe choice takes the focus, so Enter never deletes by accident.
        autoFocus
        onClick={() => setConfirming(false)}
        className={RUN_BUTTON.neutral}
      >
        Keep
      </button>
    </span>
  );
}
