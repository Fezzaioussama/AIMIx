import { API } from './endpoints';
import { request, requestBlob, UPLOAD_TIMEOUT_MS } from './client';
import type { FileListing, WorkspaceFile } from './types';

/** The signed-in user's files, newest first, with the limits that apply to them. */
export function listFiles(signal?: AbortSignal): Promise<FileListing> {
  return request<FileListing>(API.files, { signal });
}

interface UploadOptions {
  /** Overwrite a file of the same name; without it the server answers 'file_exists'. */
  replace?: boolean;
  signal?: AbortSignal;
}

/** Stores one file in the user's workspace, where their agents can read it. */
export async function uploadFile(file: File, options: UploadOptions = {}): Promise<WorkspaceFile> {
  const form = new FormData();
  form.append('files', file);
  if (options.replace) form.append('replace', 'true');
  const [stored] = await request<WorkspaceFile[]>(API.files, {
    method: 'POST',
    body: form,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    signal: options.signal,
  });
  return stored;
}

/** A file's content, fetched with the session header: a token never goes in a URL. */
export function downloadFile(path: string, signal?: AbortSignal): Promise<Blob> {
  return requestBlob(API.file(path), { timeoutMs: UPLOAD_TIMEOUT_MS, signal });
}

export function deleteFile(path: string, signal?: AbortSignal): Promise<void> {
  return request<void>(API.file(path), { method: 'DELETE', signal });
}
