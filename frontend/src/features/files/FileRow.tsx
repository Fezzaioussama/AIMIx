import { Download, Trash2, type LucideIcon } from 'lucide-react';
import { motion } from 'motion/react';
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type Ref } from 'react';

import type { WorkspaceFile } from '../../core/api/types';
import { Spinner } from '../../core/ui/Spinner';
import { fileIcon, fileName, folderOf, formatBytes, formatDate } from './fileFormat';
import type { RowAction } from './useFiles';

interface FileRowProps {
  file: WorkspaceFile;
  /** What is running on this file, if anything. */
  action: RowAction | undefined;
  /** Why the last action on this file failed; empty when it did not. */
  error: string;
  onDownload: () => void;
  onDelete: () => void;
}

const FOCUS =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400';

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon;
  /** Shows a spinner instead of the icon; the button's label names the action. */
  busy: boolean;
  buttonRef?: Ref<HTMLButtonElement>;
}

function IconButton({ icon: Icon, busy, buttonRef, ...rest }: IconButtonProps) {
  return (
    <button
      {...rest}
      ref={buttonRef}
      type="button"
      className={`grid size-9 shrink-0 place-items-center rounded-lg text-slate-300 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS}`}
    >
      {busy ? (
        <Spinner decorative className="size-4" />
      ) : (
        <Icon aria-hidden="true" className="size-4" />
      )}
    </button>
  );
}

/** The file's type icon, name, and folder, size and date. */
function FileSummary({ file }: { file: WorkspaceFile }) {
  const Icon = fileIcon(file.type);
  const folder = folderOf(file.path);
  return (
    <>
      <span
        aria-hidden="true"
        className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/[0.05] text-sky-300"
      >
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-100" title={file.path}>
          {fileName(file.path)}
        </p>
        <p className="text-xs break-words text-slate-400">
          {folder && `${folder} · `}
          {formatBytes(file.size)} ·{' '}
          <time dateTime={file.modified_at} className="whitespace-nowrap">
            {formatDate(file.modified_at)}
          </time>
        </p>
      </div>
    </>
  );
}

/** Asks before deleting. Focus starts on Cancel, the safe answer; Escape cancels too. */
function ConfirmDelete({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => cancel.current?.focus(), []);

  return (
    <div
      role="group"
      aria-label="Confirm delete"
      onKeyDown={(event) => {
        if (event.key === 'Escape') onCancel();
      }}
      className="mt-3 flex flex-wrap items-center justify-end gap-2 rounded-lg bg-white/[0.04] px-3 py-2 text-sm"
    >
      <span className="mr-auto text-slate-200">Delete this file? This cannot be undone.</span>
      <button
        ref={cancel}
        type="button"
        onClick={onCancel}
        className={`rounded-lg border border-white/15 px-3 py-1.5 text-slate-100 transition-colors hover:bg-white/10 ${FOCUS}`}
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={onConfirm}
        className={`rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-1.5 font-medium text-red-200 transition-colors hover:bg-red-500/20 ${FOCUS}`}
      >
        Delete
      </button>
    </div>
  );
}

/** One file: what it is, with download and delete (after a confirmation). */
export function FileRow({ file, action, error, onDownload, onDelete }: FileRowProps) {
  const [confirming, setConfirming] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const name = fileName(file.path);

  function cancel() {
    setConfirming(false);
    deleteButton.current?.focus();
  }

  function confirm() {
    setConfirming(false);
    onDelete();
  }

  return (
    <motion.li initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="px-4 py-3">
      <div className="flex items-center gap-3">
        <FileSummary file={file} />
        <IconButton
          icon={Download}
          busy={action === 'download'}
          disabled={action !== undefined}
          aria-label={`Download ${name}`}
          onClick={onDownload}
        />
        <IconButton
          icon={Trash2}
          busy={action === 'delete'}
          disabled={action !== undefined}
          aria-label={`Delete ${name}`}
          aria-expanded={confirming}
          onClick={() => setConfirming(true)}
          buttonRef={deleteButton}
        />
      </div>
      {confirming && <ConfirmDelete onCancel={cancel} onConfirm={confirm} />}
      {error && (
        <p role="alert" className="mt-2 text-xs text-amber-300">
          {error}
        </p>
      )}
    </motion.li>
  );
}
