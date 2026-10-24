import { API } from './endpoints';
import { request, UPLOAD_TIMEOUT_MS } from './client';
import type { ExtractedDocument } from './types';

/**
 * The kinds of file the server reads, and their extensions: the one list behind the
 * file picker's `accept` and any copy that names the formats. It mirrors READERS in
 * backend/api/services/documents/readers.py, which decides for real.
 */
export const DOCUMENT_FORMATS = [
  { kind: 'PDF', extensions: ['.pdf'] },
  { kind: 'Word', extensions: ['.docx'] },
  { kind: 'Excel', extensions: ['.xlsx'] },
  { kind: 'PowerPoint', extensions: ['.pptx'] },
  {
    kind: 'image',
    extensions: ['.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp', '.gif'],
  },
  { kind: 'HTML', extensions: ['.html', '.htm'] },
  { kind: 'CSV', extensions: ['.csv', '.tsv'] },
  {
    kind: 'text',
    extensions: ['.txt', '.md', '.markdown', '.json', '.yaml', '.yml', '.xml', '.log', '.rst'],
  },
] as const;

/** Every extension above, for a file input's `accept`. */
export const DOCUMENT_ACCEPT = DOCUMENT_FORMATS.flatMap((format) => format.extensions).join(',');

/** "PDF, Word, …, CSV or text", to write "a … file". */
export const DOCUMENT_KINDS = orList(DOCUMENT_FORMATS.map((format) => format.kind));

function orList(items: readonly string[]): string {
  return `${items.slice(0, -1).join(', ')} or ${items[items.length - 1]}`;
}

/**
 * Has the server read a document — PDF, Office file, image (by text recognition),
 * HTML or text — and return its text. Nothing is stored: the caller puts the text in
 * a run input.
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
