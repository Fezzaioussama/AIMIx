import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

import { PAGE_URL_MAX_LENGTH } from '../../core/api/documents';
import { toWebAddress } from './webLinks';

interface WebPageFieldProps {
  /** The field's id, for the `aria-controls` of the button that opens it. */
  id: string;
  open: boolean;
  /** A page cannot be read now (another document is being read, say). */
  busy?: boolean;
  /** Gets the address to read, https:// added when it was left out. */
  onRead: (address: string) => void;
  /** Escape: the caller closes the field and takes focus back. */
  onClose: () => void;
  className?: string;
}

const INPUT =
  'min-h-11 min-w-0 flex-1 rounded-lg border border-white/10 bg-slate-950/60 px-3 text-sm text-slate-100 placeholder:text-slate-400 focus-visible:outline-2 focus-visible:outline-sky-400 sm:min-h-9';
const BUTTON =
  'inline-flex min-h-11 shrink-0 items-center rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 text-sm font-medium text-sky-100 transition-colors enabled:hover:bg-sky-400/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-9';

/** Opens by animating its grid row, as FoldablePanel's `Foldable` does; out of reach shut. */
function Reveal({
  id,
  open,
  className,
  children,
}: {
  id: string;
  open: boolean;
  className: string;
  children: ReactNode;
}) {
  return (
    <div
      id={id}
      inert={!open}
      aria-hidden={!open}
      className={`grid transition-[grid-template-rows,opacity] duration-250 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none ${open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'} ${className}`}
    >
      <div className="min-h-0 min-w-0 overflow-hidden">{children}</div>
    </div>
  );
}

/**
 * A link's field, revealed in place: type or paste an address, then "Read page" or Enter
 * reads it (Enter never submits a surrounding form); Escape closes it.
 */
export function WebPageField(props: WebPageFieldProps) {
  const { id, open, busy = false, onRead, onClose, className = '' } = props;
  const [typed, setTyped] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const address = toWebAddress(typed);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  function read() {
    if (address === null || busy) return;
    onRead(address);
    setTyped('');
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter' && event.key !== 'Escape') return;
    event.preventDefault();
    if (event.key === 'Enter') read();
    else onClose();
  }

  return (
    <Reveal id={id} open={open} className={className}>
      {/* The padding keeps the focus rings inside the clipped row. */}
      <div className="flex gap-2 p-1">
        <input
          ref={input}
          type="url"
          inputMode="url"
          aria-label="Link to a web page"
          placeholder="Paste a link (https://…)"
          maxLength={PAGE_URL_MAX_LENGTH}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          onKeyDown={onKeyDown}
          className={INPUT}
        />
        <button type="button" disabled={address === null || busy} onClick={read} className={BUTTON}>
          Read page
        </button>
      </div>
    </Reveal>
  );
}
