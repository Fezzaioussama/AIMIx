import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { deleteFile, downloadFile, listFiles } from '../../core/api/files';
import type { FileListing, WorkspaceFile } from '../../core/api/types';
import { fileName, withoutFile } from './fileFormat';
import { saveBlob } from './saveBlob';
import { messageOf, useFileUploads, type Lifetime, type SetListing } from './useFileUploads';

/** What is running on one file's row. */
export type RowAction = 'download' | 'delete';

/** The request behind a row action, cancelled with the screen. */
type RowTask = (signal: AbortSignal) => Promise<void>;

/** Why a download or a delete of one file failed, shown next to that file. */
export interface RowError {
  path: string;
  message: string;
}

/** One AbortController per mount: unmounting aborts every request made through it. */
function useLifetime(): Lifetime {
  const lifetime = useRef(new AbortController());
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  return lifetime;
}

function useListing(lifetime: Lifetime) {
  const [listing, setListing] = useState<FileListing | null>(null);
  const [loadError, setLoadError] = useState('');
  // Runs after useLifetime's effect, so the signal is this mount's.
  useEffect(() => {
    const { signal } = lifetime.current;
    listFiles(signal)
      .then((loaded) => {
        if (!signal.aborted) setListing(loaded);
      })
      .catch((cause: unknown) => {
        if (!signal.aborted) setLoadError(messageOf(cause, 'Could not load files.'));
      });
  }, [lifetime]);
  return { listing, setListing, loadError };
}

/** Deletes a file; one that is already gone is what was asked for. */
async function deleteIfPresent(path: string, signal: AbortSignal): Promise<void> {
  try {
    await deleteFile(path, signal);
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.code === 'not_found')) throw cause;
  }
}

function withoutKey<T>(map: ReadonlyMap<string, T>, key: string): ReadonlyMap<string, T> {
  const next = new Map(map);
  next.delete(key);
  return next;
}

/** Download and delete, each shown busy (and failed, if so) on its own row. */
function useRowActions(
  lifetime: Lifetime,
  setListing: SetListing,
  setNotice: (text: string) => void,
) {
  const [pending, setPending] = useState<ReadonlyMap<string, RowAction>>(new Map());
  const [rowError, setRowError] = useState<RowError | null>(null);

  const track = useCallback(
    async (file: WorkspaceFile, kind: RowAction, task: RowTask) => {
      const { signal } = lifetime.current;
      setPending((current) => new Map(current).set(file.path, kind));
      setRowError(null);
      setNotice('');
      try {
        await task(signal);
      } catch (cause) {
        if (signal.aborted) return;
        setRowError({ path: file.path, message: messageOf(cause, `Could not ${kind} the file.`) });
      } finally {
        if (!signal.aborted) setPending((current) => withoutKey(current, file.path));
      }
    },
    [lifetime, setNotice],
  );

  const download = useCallback(
    (file: WorkspaceFile) =>
      track(file, 'download', async (signal) => {
        const content = await downloadFile(file.path, signal);
        if (!signal.aborted) saveBlob(content, fileName(file.path));
      }),
    [track],
  );

  const remove = useCallback(
    (file: WorkspaceFile) =>
      track(file, 'delete', async (signal) => {
        await deleteIfPresent(file.path, signal);
        if (signal.aborted) return;
        setListing((current) => current && withoutFile(current, file.path));
        setNotice(`${fileName(file.path)} deleted.`);
      }),
    [setListing, setNotice, track],
  );

  return { pending, rowError, download, remove };
}

/**
 * State and transport for the Files screen, kept out of the components (§2): the
 * listing, uploads, and download/delete per row. Every request carries the
 * signal of this mount, so nothing updates state after the screen is gone.
 */
export function useFiles() {
  const lifetime = useLifetime();
  const { listing, setListing, loadError } = useListing(lifetime);
  const [notice, setNotice] = useState('');
  const uploads = useFileUploads(lifetime, setListing, setNotice);
  const rows = useRowActions(lifetime, setListing, setNotice);

  return {
    listing,
    loadError,
    notice,
    uploading: uploads.uploading,
    problems: uploads.problems,
    pending: rows.pending,
    rowError: rows.rowError,
    actions: {
      upload: uploads.upload,
      replace: uploads.replace,
      dismiss: uploads.dismiss,
      download: rows.download,
      remove: rows.remove,
    },
  };
}
