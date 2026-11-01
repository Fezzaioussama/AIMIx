import { Globe } from 'lucide-react';
import { useId, useRef, useState } from 'react';

import { ATTACH_CONTROL } from './attachStyles';
import { WebPageField } from './WebPageField';

interface AttachWebPageProps {
  /** Reads the page at the address into the input. */
  onRead: (address: string) => void;
  /** The form is busy: the control cannot be used at all. */
  disabled?: boolean;
  /** Another document is being read: the field opens, but reads nothing yet. */
  busy?: boolean;
}

/**
 * "Add a web page" beside "Attach a document": a button that reveals a field for a link,
 * whose page the server reads like a document. The field takes a whole row of the wrapping
 * attach row. Closing it, by reading or by Escape, gives focus back to the button.
 */
export function AttachWebPage({ onRead, disabled = false, busy = false }: AttachWebPageProps) {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const id = useId();

  function close() {
    setOpen(false);
    toggle.current?.focus();
  }

  return (
    <>
      <button
        ref={toggle}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        disabled={disabled}
        onClick={() => setOpen(!open)}
        className={ATTACH_CONTROL}
      >
        <Globe aria-hidden="true" className="size-3.5" />
        Add a web page
      </button>
      <WebPageField
        id={id}
        open={open && !disabled}
        busy={busy}
        onRead={(address) => {
          onRead(address);
          close();
        }}
        onClose={close}
        // Its own line of the wrapping row; the negative margin cancels the row's gap, so a
        // closed field adds no space.
        className="order-last -mt-2 basis-full"
      />
    </>
  );
}
