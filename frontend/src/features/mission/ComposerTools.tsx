import { LinkIcon, Paperclip, SendHorizontal } from 'lucide-react';
import { useRef, useState, type RefObject } from 'react';

import { DOCUMENT_ACCEPT } from '../../core/api/documents';
import { chosenFiles } from '../../core/chosenFiles';
import { MicButton } from '../../core/voice/MicButton';

/** The look of the message box's icon buttons; 44px for a finger (a phone, a touch screen). */
const TOOL_BUTTON =
  'grid size-11 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-slate-300 transition duration-300 hover:border-sky-400/40 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 sm:size-10 pointer-coarse:size-11';

const SEND_BUTTON =
  'grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-sky-600 via-indigo-600 to-purple-600 text-white transition duration-300 enabled:hover:shadow-[0_0_24px_rgba(99,102,241,0.6)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-40 sm:size-10 pointer-coarse:size-11';

/** The link field of the message box: whether it is open, and the button that opens it. */
export interface LinkField {
  id: string;
  open: boolean;
  toggle: RefObject<HTMLButtonElement | null>;
  flip: () => void;
  /** Closes it and gives focus back to its button. */
  close: () => void;
}

export function useLinkField(id: string): LinkField {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  return {
    id,
    open,
    toggle,
    flip: () => setOpen((now) => !now),
    close: () => {
      setOpen(false);
      toggle.current?.focus();
    },
  };
}

interface ComposerToolbarProps {
  onFiles: (files: File[]) => void;
  link: LinkField;
  /** What dictating does here, for its button's name, and where the words go. */
  micLabel: string;
  onTranscript: (text: string) => void;
  /** Something can be sent. */
  ready: boolean;
}

/** Under the text: attach documents, add a link, dictate, send. */
export function ComposerToolbar({
  onFiles,
  link,
  micLabel,
  onTranscript,
  ready,
}: ComposerToolbarProps) {
  return (
    <div className="mt-1 flex items-center justify-end gap-1.5">
      <FilesButton onFiles={onFiles} />
      <button
        ref={link.toggle}
        type="button"
        title="Add a link"
        aria-label="Add a link"
        aria-expanded={link.open}
        aria-controls={link.id}
        onClick={link.flip}
        className={`${TOOL_BUTTON} ${link.open ? 'border-sky-400/40 text-white' : ''}`}
      >
        <LinkIcon aria-hidden="true" className="size-5" />
      </button>
      <MicButton label={micLabel} onTranscript={onTranscript} />
      <button type="submit" disabled={!ready} aria-label="Send" className={SEND_BUTTON}>
        <SendHorizontal aria-hidden="true" className="size-5" />
      </button>
    </div>
  );
}

/** "Attach a document", several at once. The file input is real but visually hidden, so it
 * keeps its name and its keyboard. */
function FilesButton({ onFiles }: { onFiles: (files: File[]) => void }) {
  return (
    <label
      title="Attach a document"
      className={`${TOOL_BUTTON} cursor-pointer has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-sky-400`}
    >
      <input
        type="file"
        multiple
        accept={DOCUMENT_ACCEPT}
        aria-label="Attach a document"
        onChange={(event) => {
          const files = chosenFiles(event);
          if (files.length > 0) onFiles(files);
        }}
        className="sr-only"
      />
      <Paperclip aria-hidden="true" className="size-5" />
    </label>
  );
}
