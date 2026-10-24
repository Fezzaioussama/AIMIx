import { CloudUpload, X } from 'lucide-react';
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react';

import type { FileListing } from '../../core/api/types';
import { GlowButton } from '../../core/ui/GlowButton';
import { describeTypes, formatBytes } from './fileFormat';
import type { UploadProblem } from './useFiles';

interface UploadPanelProps {
  listing: FileListing;
  /** The name of the file on its way up; empty when nothing is. */
  uploading: string;
  problems: UploadProblem[];
  onUpload: (files: File[]) => void;
  onReplace: (problem: UploadProblem) => void;
  onDismiss: (problem: UploadProblem) => void;
}

const SMALL_BUTTON =
  'rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-100 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50';

/** A file dropped just beside the zone would otherwise replace the page with itself. */
function useDropGuard() {
  useEffect(() => {
    const hold = (event: globalThis.DragEvent) => {
      if (event.dataTransfer?.types.includes('Files')) event.preventDefault();
    };
    window.addEventListener('dragover', hold);
    window.addEventListener('drop', hold);
    return () => {
      window.removeEventListener('dragover', hold);
      window.removeEventListener('drop', hold);
    };
  }, []);
}

/** Files that were refused, each with its reason and, for a taken name, "Replace". */
function ProblemList({
  problems,
  busy,
  onReplace,
  onDismiss,
}: Pick<UploadPanelProps, 'problems' | 'onReplace' | 'onDismiss'> & { busy: boolean }) {
  return (
    <ul className="mx-auto mt-4 max-w-xl space-y-2 text-left">
      {problems.map((problem) => (
        <li
          key={problem.id}
          className="flex items-start gap-2 rounded-lg border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2"
        >
          <p role="alert" className="min-w-0 flex-1 text-sm text-amber-200">
            <span className="font-medium break-all">{problem.file.name}</span>: {problem.message}
          </p>
          {problem.canReplace && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onReplace(problem)}
              className={SMALL_BUTTON}
            >
              Replace
            </button>
          )}
          <button
            type="button"
            onClick={() => onDismiss(problem)}
            aria-label={`Dismiss the message about ${problem.file.name}`}
            className="rounded-md p-1 text-slate-300 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </li>
      ))}
    </ul>
  );
}

/**
 * Upload by button or by dropping files on the panel. The file input is hidden; the
 * "Choose files" button opens it, so the keyboard path is an ordinary button.
 */
export function UploadPanel({
  listing,
  uploading,
  problems,
  onUpload,
  onReplace,
  onDismiss,
}: UploadPanelProps) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const busy = uploading !== '';
  useDropGuard();

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const files = [...(event.target.files ?? [])];
    // Reset, so choosing the same file again still counts as a change.
    event.target.value = '';
    if (files.length > 0) onUpload(files);
  }

  function drop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    const files = [...event.dataTransfer.files];
    if (files.length > 0 && !busy) onUpload(files);
  }

  function leave(event: DragEvent<HTMLElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
  }

  return (
    <section
      aria-labelledby="upload-title"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(!busy);
      }}
      onDragLeave={leave}
      onDrop={drop}
      className={`rounded-2xl border border-dashed px-5 py-8 text-center transition-colors ${
        dragging ? 'border-sky-400/70 bg-sky-400/[0.06]' : 'border-white/15 bg-slate-900/40'
      }`}
    >
      <CloudUpload aria-hidden="true" className="mx-auto mb-3 size-8 text-sky-300" />
      <h2 id="upload-title" className="text-base font-semibold text-slate-100">
        Add files for your agents
      </h2>
      <p className="mt-1 mb-4 text-sm text-slate-400">Drop files here, or choose them.</p>
      <GlowButton size="sm" busy={busy} onClick={() => input.current?.click()}>
        {busy ? 'Uploading…' : 'Choose files'}
      </GlowButton>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        aria-label="Files to upload"
        accept={listing.allowed_extensions.join(',')}
        onChange={choose}
      />
      <p className="mt-3 text-xs text-slate-400">
        {describeTypes(listing.allowed_extensions)}, up to {formatBytes(listing.max_file_bytes)}{' '}
        each
      </p>
      {problems.length > 0 && (
        <ProblemList problems={problems} busy={busy} onReplace={onReplace} onDismiss={onDismiss} />
      )}
    </section>
  );
}
