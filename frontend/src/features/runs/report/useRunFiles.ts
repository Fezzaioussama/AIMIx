import { useCallback, useEffect, useState } from 'react';

import { listFiles } from '../../../core/api/files';
import type { Run, WorkspaceFile } from '../../../core/api/types';
import { useLatest } from '../../../core/hooks/useLatest';
import { downloadAndSave } from '../../files/fileDownload';
import { useLifetime, type RowError } from '../../files/useFiles';
import { finishedStepCount } from '../runStatus';
import { mayHaveSavedFiles, savedDuringRun } from './runFiles';

/** What a file's row says when its download fails (brief §7). */
const DOWNLOAD_FAILED = 'Could not download the file.';

export interface RunFilesState {
  /** The files saved while the run worked; null until they load, and when they cannot. */
  files: WorkspaceFile[] | null;
  /** The file being downloaded right now, if any. */
  busyPath: string | null;
  rowError: RowError | null;
  download: (file: WorkspaceFile) => void;
}

/**
 * The workspace's files saved while the run worked (GET /api/files, filtered by the run's
 * time window), read again each time a step finishes or the run's status changes. Nothing
 * is asked of the server while no step of the run may save a file. A list that cannot be
 * loaded, or makes no sense, hides the section rather than shouting about it.
 */
function useSavedFiles(run: Run): WorkspaceFile[] | null {
  const [files, setFiles] = useState<WorkspaceFile[] | null>(null);
  const latest = useLatest(run);
  const mayHave = mayHaveSavedFiles(run);
  const progress = `${finishedStepCount(run)}:${run.status}`;

  useEffect(() => {
    if (!mayHave) return;
    const controller = new AbortController();
    listFiles(controller.signal)
      // Filtered inside the chain, so a malformed answer counts as a failed load.
      .then((listing) => savedDuringRun(listing.files, latest.current))
      .then((saved) => {
        if (!controller.signal.aborted) setFiles(saved);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFiles(null);
      });
    return () => controller.abort();
  }, [mayHave, progress, latest]);

  return mayHave ? files : null;
}

/** "Saved during this run": its files, and a download per row, busy and failed on that row. */
export function useRunFiles(run: Run): RunFilesState {
  const files = useSavedFiles(run);
  const lifetime = useLifetime();
  const [busyPath, setBusyPath] = useState<string | null>(null);
  const [rowError, setRowError] = useState<RowError | null>(null);

  const download = useCallback(
    (file: WorkspaceFile) => {
      const { signal } = lifetime.current;
      setBusyPath(file.path);
      setRowError(null);
      downloadAndSave(file.path, signal)
        .catch(() => {
          if (!signal.aborted) setRowError({ path: file.path, message: DOWNLOAD_FAILED });
        })
        .finally(() => {
          if (!signal.aborted) setBusyPath(null);
        });
    },
    [lifetime],
  );

  return { files, busyPath, rowError, download };
}
