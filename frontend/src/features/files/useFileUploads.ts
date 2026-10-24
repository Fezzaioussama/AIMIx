import { useCallback, useRef, useState, type Dispatch, type SetStateAction } from 'react';

import { ApiError } from '../../core/api/client';
import { uploadFile } from '../../core/api/files';
import type { FileListing, WorkspaceFile } from '../../core/api/types';
import { fileName, withFile } from './fileFormat';

/** A file that could not be uploaded, and why. */
export interface UploadProblem {
  id: number;
  file: File;
  message: string;
  /** Its name is taken: uploading it again with `replace` overwrites the stored file. */
  canReplace: boolean;
}

/** One AbortController per mount; leaving the screen aborts its requests. */
export type Lifetime = { readonly current: AbortController };
export type SetListing = Dispatch<SetStateAction<FileListing | null>>;

interface UploadReport {
  started: (file: File) => void;
  stored: (entry: WorkspaceFile) => void;
  refused: (file: File, cause: unknown) => void;
}

export function messageOf(cause: unknown, fallback: string): string {
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
 * Uploads one file after another, so each refusal is reported against its own
 * file and the others still arrive. Null when the screen went away meanwhile.
 */
async function uploadEach(
  files: File[],
  replace: boolean,
  signal: AbortSignal,
  report: UploadReport,
): Promise<WorkspaceFile[] | null> {
  const stored: WorkspaceFile[] = [];
  for (const file of files) {
    report.started(file);
    try {
      const entry = await uploadFile(file, { replace, signal });
      if (signal.aborted) return null;
      stored.push(entry);
      report.stored(entry);
    } catch (cause) {
      if (signal.aborted) return null;
      report.refused(file, cause);
    }
  }
  return stored;
}

/** Uploads, their refusals, and "Replace" for a taken name. */
export function useFileUploads(
  lifetime: Lifetime,
  setListing: SetListing,
  setNotice: (text: string) => void,
) {
  const [uploading, setUploading] = useState('');
  const [problems, setProblems] = useState<UploadProblem[]>([]);
  const problemCount = useRef(0);

  const send = useCallback(
    async (files: File[], replace: boolean) => {
      setNotice('');
      const stored = await uploadEach(files, replace, lifetime.current.signal, {
        started: (file) => setUploading(file.name),
        stored: (entry) => setListing((current) => current && withFile(current, entry)),
        refused: (file, cause) => {
          problemCount.current += 1;
          const problem = problemFor(problemCount.current, file, cause);
          setProblems((current) => [...current, problem]);
        },
      });
      if (stored === null) return;
      setUploading('');
      setNotice(uploadedNotice(stored));
    },
    [lifetime, setListing, setNotice],
  );

  const forget = useCallback((problem: UploadProblem) => {
    setProblems((current) => current.filter((entry) => entry.id !== problem.id));
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
      forget(problem);
      await send([problem.file], true);
    },
    [forget, send],
  );

  return { uploading, problems, upload, replace, dismiss: forget };
}
