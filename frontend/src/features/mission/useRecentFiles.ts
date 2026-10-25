import { useEffect, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { listFiles } from '../../core/api/files';
import type { WorkspaceFile } from '../../core/api/types';

/** How many of the newest files the Results pane lists. */
export const RECENT_FILES = 5;

export interface RecentFiles {
  /** The newest files; null until the first answer. */
  files: WorkspaceFile[] | null;
  /** Why the list could not be loaded; empty when it could. */
  error: string;
}

/**
 * The newest files of the user's workspace (GET /api/files, newest first). It loads when
 * the pane opens and again whenever `refreshKey` changes: agents save files while a run
 * works, so the pane passes a key that changes when the run ends. A reload keeps the
 * earlier list on screen until the new one arrives.
 */
export function useRecentFiles(refreshKey: string): RecentFiles {
  const [files, setFiles] = useState<WorkspaceFile[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    listFiles(controller.signal)
      .then((listing) => {
        if (controller.signal.aborted) return;
        setFiles(listing.files.slice(0, RECENT_FILES));
        setError('');
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(cause, 'Could not load your files.'));
      });
    return () => controller.abort();
  }, [refreshKey]);

  return { files, error };
}
