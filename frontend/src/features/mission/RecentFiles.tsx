import { FolderOpen } from 'lucide-react';
import { Link } from 'react-router-dom';

import { fileIcon, fileName, folderOf, formatBytes, formatDate } from '../files/fileFormat';
import { useRecentFiles } from './useRecentFiles';

/** Whether a run is still working, folded into a key that changes when it ends. */
export function filesRefreshKey(runId: number | null, active: boolean): string {
  return `${runId ?? 'none'}-${active ? 'active' : 'ended'}`;
}

/**
 * The newest files in the user's workspace — what agents saved, what was uploaded —
 * with a way into the Files page, where they can be downloaded.
 */
export function RecentFiles({ refreshKey }: { refreshKey: string }) {
  const { files, error } = useRecentFiles(refreshKey);

  return (
    <section aria-labelledby="mission-files">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 id="mission-files" className="text-sm font-semibold text-slate-100">
          Recent files
        </h3>
        <Link
          to="/files"
          className="rounded text-sm font-medium text-sky-300 underline-offset-4 hover:text-sky-200 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
        >
          All files<span className="sr-only"> in your workspace</span>
        </Link>
      </div>
      {error && (
        <p role="alert" className="text-sm text-amber-300">
          {error}
        </p>
      )}
      {files === null && !error && <p className="text-sm text-slate-400">Loading your files…</p>}
      {files !== null && files.length === 0 && (
        <p className="flex items-start gap-2 text-sm text-slate-400">
          <FolderOpen aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Files your agents save appear here.
        </p>
      )}
      {files !== null && files.length > 0 && (
        <ul className="divide-y divide-white/[0.06] rounded-xl border border-white/10 bg-slate-900/50">
          {files.map((file) => {
            const Icon = fileIcon(file.type);
            const folder = folderOf(file.path);
            return (
              <li key={file.path} className="flex items-center gap-3 px-3 py-2.5">
                <Icon aria-hidden="true" className="size-4 shrink-0 text-sky-300" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-100" title={file.path}>
                    {fileName(file.path)}
                  </p>
                  <p className="text-xs break-words text-slate-400">
                    {folder && `${folder} · `}
                    {formatBytes(file.size)} · {formatDate(file.modified_at)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
