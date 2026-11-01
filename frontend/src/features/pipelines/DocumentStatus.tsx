import { INLINE_ACTION } from './attachStyles';
import type { DocumentReader, HeldDocument } from './useAttachDocument';

interface DocumentStatusProps {
  reader: DocumentReader;
  /** After "Add it anyway" or "Leave it out": where focus goes once the question is gone. */
  onSettled: () => void;
}

/**
 * The line under a run input's attach controls: what is being read and what was added
 * (a polite live region, there even when empty, so screen readers follow it), why the
 * last one could not be read, or a document waiting for the person's say-so.
 */
export function DocumentStatus({ reader, onSettled }: DocumentStatusProps) {
  const { reading, notice, error, held } = reader;
  return (
    <>
      <p
        role="status"
        className={`mt-1.5 empty:mt-0 ${reading ? 'text-slate-300' : 'text-emerald-300'}`}
      >
        {reading ? `Reading ${reading}…` : notice}
      </p>
      {error && (
        <p role="alert" className="mt-1.5 text-amber-300">
          {error}
        </p>
      )}
      {held && (
        <HeldWarning
          held={held}
          onKeep={() => {
            reader.keep();
            onSettled();
          }}
          onDismiss={() => {
            reader.dismiss();
            onSettled();
          }}
        />
      )}
    </>
  );
}

interface HeldWarningProps {
  held: HeldDocument;
  onKeep: () => void;
  onDismiss: () => void;
}

/** A document that would put the run past its limit: added only if the person says so. */
function HeldWarning({ held, onKeep, onDismiss }: HeldWarningProps) {
  return (
    <div className="mt-1.5 rounded-lg border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2">
      <p role="alert" className="text-amber-200">
        {held.warning}
      </p>
      <div className="mt-1 flex flex-wrap gap-x-4">
        <button type="button" onClick={onKeep} className={INLINE_ACTION}>
          Add it anyway
        </button>
        <button type="button" onClick={onDismiss} className={INLINE_ACTION}>
          Leave it out
        </button>
      </div>
    </div>
  );
}

/** Under an input that holds only a link: agents would get the address, not the page. */
export function LinkNudge({ disabled, onRead }: { disabled: boolean; onRead: () => void }) {
  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-slate-300">
      <span>Agents can’t open links on their own.</span>
      <button type="button" disabled={disabled} onClick={onRead} className={INLINE_ACTION}>
        Read this page into the box
      </button>
    </p>
  );
}
