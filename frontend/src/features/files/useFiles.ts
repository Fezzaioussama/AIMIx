import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { deleteFile, downloadFile, listFiles, uploadFile } from '../../core/api/files';
import type { FileListing, WorkspaceFile } from '../../core/api/types';
import { fileName, withFile, withoutFile } from './fileFormat';
import { saveBlob } from './saveBlob';

/** A file that could not be uploaded, and why. */
export interface UploadProblem {
  id: number;
  file: File;
  message: string;
  /** Its name is taken: uploading it again with `replace` overwrites the stored file. */
  canReplace: boolean;
}

/** What is running on one file's row. */
export type RowAction = 'download' | 'delete';

/** Why a download or a delete of one file failed, shown next to that file. */
export interface RowError {
  path: string;
  message: string;
}

function messageOf(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}

function problemFor(id: number, file: File, cause: unknown): UploadProblem {
  const taken = cause instanceof ApiError && cause.code === 'file_exists';
  return {
    id,
    file,
    // The server's wording also speaks to agents; here the Replace button answers it.
    message: taken
      ? 'A file with this name already exists.'
      : messageOf(cause, 'The file could not be uploaded.'),
    canReplace: taken,
  };
}

function uploadedNotice(stored: WorkspaceFile[]): string {
  if (stored.length === 0) return '';
  return stored.length === 1
    ? `${fileName(stored[0].path)} uploaded.`
    : `${stored.length} files uploaded.`;
}

/**
 * State and transport for the Files screen, kept out of the components (§2). Every
 * request shares one AbortController that leaving the screen aborts, so nothing
 * updates state after teardown. Uploads go one file at a time, so each refusal is
 * reported against its own file and the rest still arrive.
 */
export function useFiles() {
  const [listing, setListing] = useState<FileListing | null>(null);
  const [loadError, setLoadError] = useState('');
  const [uploading, setUploading] = useState('');
  const [problems, setProblems] = useState<UploadProblem[]>([]);
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<ReadonlyMap<string, RowAction>>(new Map());
  const [rowError, setRowError] = useState<RowError | null>(null);
  const lifetime = useRef(new AbortController());
  const problemCount = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    listFiles(controller.signal)
      .then((loaded) => {
        if (!controller.signal.aborted) setListing(loaded);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setLoadError(messageOf(cause, 'Could not load files.'));
      });
    return () => controller.abort();
  }, []);

  const send = useCallback(async (files: File[], replace: boolean) => {
    const { signal } = lifetime.current;
    const stored: WorkspaceFile[] = [];
    setNotice('');
    for (const file of files) {
      setUploading(file.name);
      try {
        const entry = await uploadFile(file, { replace, signal });
        if (signal.aborted) return;
        stored.push(entry);
        setListing((current) => current && withFile(current, entry));
      } catch (cause) {
        if (signal.aborted) return;
        problemCount.current += 1;
        const problem = problemFor(problemCount.current, file, cause);
        setProblems((current) => [...current, problem]);
      }
    }
    setUploading('');
    setNotice(uploadedNotice(stored));
  }, []);

  const upload = useCallback(
    async (files: File[]) => {
      setProblems([]);
      await send(files, false);
    },
    [send],
  );

  const replace = useCallback(
    async (problem: UploadProblem) => {
      setProblems((current) => current.filter((entry) => entry.id !== problem.id));
      await send([problem.file], true);
    },
    [send],
  );

  const dismiss = useCallback((problem: UploadProblem) => {
    setProblems((current) => current.filter((entry) => entry.id !== problem.id));
  }, []);

  const track = useCallback(
    async (
      file: WorkspaceFile,
      kind: RowAction,
      action: (signal: AbortSignal) => Promise<void>,
    ) => {
      const { signal } = lifetime.current;
      setPending((current) => new Map(current).set(file.path, kind));
      setRowError(null);
      setNotice('');
      try {
        await action(signal);
      } catch (cause) {
        if (!signal.aborted)
          setRowError({
            path: file.path,
            message: messageOf(cause, `Could not ${kind} the file.`),
          });
      } finally {
        if (!signal.aborted)
          setPending((current) => {
            const next = new Map(current);
            next.delete(file.path);
            return next;
          });
      }
    },
    [],
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
        try {
          await deleteFile(file.path, signal);
        } catch (cause) {
          // Already gone is what was asked for.
          if (!(cause instanceof ApiError && cause.code === 'not_found')) throw cause;
        }
        if (signal.aborted) return;
        setListing((current) => current && withoutFile(current, file.path));
        setNotice(`${fileName(file.path)} deleted.`);
      }),
    [track],
  );

  return {
    listing,
    loadError,
    uploading,
    problems,
    notice,
    pending,
    rowError,
    actions: { upload, replace, dismiss, download, remove },
  };
}
