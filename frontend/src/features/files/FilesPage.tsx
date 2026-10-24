import { FolderOpen } from 'lucide-react';

import type { FileListing } from '../../core/api/types';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { BlurText } from '../../core/ui/reactbits/BlurText';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { FileRow } from './FileRow';
import { formatBytes } from './fileFormat';
import { UploadPanel } from './UploadPanel';
import { useFiles } from './useFiles';

/** How much of the storage limit the files use: a line of text and a bar. */
function StorageUsage({ listing }: { listing: FileListing }) {
  const percent = Math.min(100, (listing.used_bytes / listing.quota_bytes) * 100);
  return (
    <div className="mt-4">
      <p className="mb-1.5 text-xs text-slate-400">
        {formatBytes(listing.used_bytes)} of {formatBytes(listing.quota_bytes)} used
      </p>
      <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-sky-400 via-indigo-500 to-purple-500"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

function FilesHeader({ listing }: { listing: FileListing | null }) {
  return (
    <header className="mb-6">
      <p className="mb-1 text-xs font-semibold tracking-widest uppercase">
        <ShinyText className="text-sky-400/80">Workspace</ShinyText>
      </p>
      <h1 className="text-3xl font-extrabold tracking-tight">
        <BlurText text="Files" animateBy="letters" delay={40} />
      </h1>
      <p className="mt-2 text-sm text-slate-400">
        Download what your agents save, and add files for them to read. Only you and your agents can
        see these files.
      </p>
      {listing && <StorageUsage listing={listing} />}
    </header>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/40 px-6 py-10 text-center">
      <FolderOpen aria-hidden="true" className="mx-auto mb-3 size-8 text-slate-400" />
      <h2 className="text-base font-semibold text-slate-100">No files yet</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-400">
        Files your agents save appear here. Agents with file tools can also read the files you
        upload.
      </p>
    </div>
  );
}

type FilesState = ReturnType<typeof useFiles>;

/** The files, or what this page is for when there are none yet. */
function FileList({ state }: { state: FilesState & { listing: FileListing } }) {
  const { listing, pending, rowError, actions } = state;
  if (listing.files.length === 0) return <EmptyState />;
  return (
    <ul
      aria-label="Your files"
      className="divide-y divide-white/[0.06] rounded-2xl border border-white/10 bg-slate-900/60"
    >
      {listing.files.map((file) => (
        <FileRow
          key={file.path}
          file={file}
          action={pending.get(file.path)}
          error={rowError?.path === file.path ? rowError.message : ''}
          onDownload={() => void actions.download(file)}
          onDelete={() => void actions.remove(file)}
        />
      ))}
    </ul>
  );
}

/** Upload, an announced status line, and the list. */
function FilesBody({ state }: { state: FilesState & { listing: FileListing } }) {
  const { listing, uploading, problems, notice, actions } = state;
  return (
    <>
      <UploadPanel
        listing={listing}
        uploading={uploading}
        problems={problems}
        onUpload={(files) => void actions.upload(files)}
        onReplace={(problem) => void actions.replace(problem)}
        onDismiss={actions.dismiss}
      />
      <p
        role="status"
        className={`my-3 min-h-5 truncate text-sm ${uploading ? 'text-slate-300' : 'text-emerald-300'}`}
      >
        {uploading ? `Uploading ${uploading}…` : notice}
      </p>
      <FileList state={state} />
    </>
  );
}

export function FilesPage() {
  const state = useFiles();
  const { listing, loadError } = state;

  return (
    <div className="min-h-[calc(100vh-60px)] px-4 py-10 text-slate-50">
      <div className="mx-auto max-w-3xl">
        <FilesHeader listing={listing} />
        {loadError && (
          <p role="alert" className="text-sm text-red-400">
            {loadError}
          </p>
        )}
        {!listing && !loadError && <BusyNotice className="py-16">Loading your files…</BusyNotice>}
        {listing && <FilesBody state={{ ...state, listing }} />}
      </div>
    </div>
  );
}
