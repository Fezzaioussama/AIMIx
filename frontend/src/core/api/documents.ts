import { API } from './endpoints';
import { request, UPLOAD_TIMEOUT_MS } from './client';
import type { ExtractedDocument } from './types';

/**
 * Has the server read a PDF, Word, HTML or text file and return its text. Nothing is
 * stored: the caller puts the text in a run input.
 */
export function extractDocument(file: File, signal?: AbortSignal): Promise<ExtractedDocument> {
  const form = new FormData();
  form.append('file', file);
  return request<ExtractedDocument>(API.extractDocument, {
    method: 'POST',
    body: form,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    signal,
  });
}
