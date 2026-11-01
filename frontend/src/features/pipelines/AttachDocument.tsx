import { Paperclip } from 'lucide-react';
import { useEffect, useRef, type Ref } from 'react';

import { DOCUMENT_ACCEPT, DOCUMENT_KINDS } from '../../core/api/documents';
import { chosenFiles } from '../../core/chosenFiles';
import { useLatest } from '../../core/hooks/useLatest';
import { filePickerClass } from './attachStyles';
import { AttachWebPage } from './AttachWebPage';
import { DocumentStatus, LinkNudge } from './DocumentStatus';
import { documentLimitWarning, holdsDocument, placeDocument } from './pipelineInputs';
import { useAttachDocument } from './useAttachDocument';
import { bareLink } from './webLinks';

interface AttachDocumentProps {
  /** The input's text: a document goes after it; a page read from the link it holds alone
   * takes the link's place. */
  value: string;
  onChange: (value: string) => void;
  /** Characters the run's other inputs take: a document that would put the run past its
   * limit waits for the person's say-so. */
  others?: number;
  disabled?: boolean;
  /** Told what is being read ('' once nothing is), so the form can wait for it. */
  onReading?: (name: string) => void;
}

/**
 * The controls under a run input: "Attach a document" (a PDF, Office file, image or text
 * file, DOCUMENT_FORMATS) and "Add a web page" (a link the server opens). The text is added
 * to the input, where it can still be read and edited, and one status line says how it
 * went. The file input is visually hidden but real, so the label is its accessible name and
 * the keyboard works without script.
 */
export function AttachDocument({
  value,
  onChange,
  others = 0,
  disabled = false,
  onReading,
}: AttachDocumentProps) {
  const reader = useAttachDocument({
    add: (document, link) => onChange(placeDocument(value, document, link)),
    warning: (document, link) =>
      documentLimitWarning(document, others + placeDocument(value, document, link).length),
  });
  const told = useLatest(onReading);
  useEffect(() => {
    told.current?.(reader.reading);
    return () => told.current?.('');
  }, [reader.reading, told]);
  const picker = useRef<HTMLInputElement>(null);
  const busy = reader.reading !== '';
  const link = bareLink(value);
  // "… added" stays only while the input still holds that document's text.
  const shown =
    reader.added === '' || holdsDocument(value, reader.added) ? reader : { ...reader, notice: '' };

  return (
    <div className="mt-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <FilePicker ref={picker} reading={busy} disabled={disabled} onFile={reader.readFile} />
        <AttachWebPage onRead={reader.readPage} disabled={disabled} busy={busy} />
        <span className="text-slate-400">{DOCUMENT_KINDS} file</span>
      </div>
      {link !== null && (
        <LinkNudge disabled={disabled || busy} onRead={() => reader.readPage(link)} />
      )}
      <DocumentStatus reader={shown} onSettled={() => picker.current?.focus()} />
    </div>
  );
}

interface FilePickerProps {
  reading: boolean;
  disabled: boolean;
  onFile: (file: File) => void;
  ref: Ref<HTMLInputElement>;
}

function FilePicker({ reading, disabled, onFile, ref }: FilePickerProps) {
  return (
    <label className={filePickerClass(!disabled && !reading)}>
      <input
        ref={ref}
        type="file"
        accept={DOCUMENT_ACCEPT}
        className="sr-only"
        disabled={disabled || reading}
        onChange={(event) => {
          const [file] = chosenFiles(event);
          if (file) onFile(file);
        }}
      />
      <Paperclip aria-hidden="true" className="size-3.5" />
      {reading ? 'Reading…' : 'Attach a document'}
    </label>
  );
}
