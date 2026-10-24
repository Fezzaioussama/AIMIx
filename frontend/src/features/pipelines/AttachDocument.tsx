import { Paperclip } from 'lucide-react';
import type { ChangeEvent } from 'react';

import type { ExtractedDocument } from '../../core/api/types';
import { useAttachDocument } from './useAttachDocument';

interface AttachDocumentProps {
  onDocument: (document: ExtractedDocument) => void;
  disabled?: boolean;
}

/**
 * "Attach a document" under a run input: pick a PDF, Word, CSV, text… file and its
 * text is added to the input, where it can still be read and edited. The file input
 * is visually hidden but real, so the label is its accessible name and the keyboard
 * works without script.
 */
export function AttachDocument({ onDocument, disabled = false }: AttachDocumentProps) {
  const { reading, error, notice, attach } = useAttachDocument(onDocument);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset, so choosing the same file again still counts as a change.
    event.target.value = '';
    if (file) void attach(file);
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <label
        className={`inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 font-medium text-slate-200 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-sky-400 ${
          disabled || reading
            ? 'cursor-not-allowed opacity-60'
            : 'cursor-pointer hover:border-white/25 hover:bg-white/10'
        }`}
      >
        <input
          type="file"
          className="sr-only"
          disabled={disabled || reading}
          onChange={handleChange}
        />
        <Paperclip aria-hidden="true" className="size-3.5" />
        {reading ? 'Reading…' : 'Attach a document'}
      </label>
      <span className="text-slate-400">PDF, Word, CSV, text and more</span>
      {notice && (
        <span role="status" className="text-emerald-300">
          {notice}
        </span>
      )}
      {error && (
        <span role="alert" className="text-amber-300">
          {error}
        </span>
      )}
    </div>
  );
}
