/** A deliverable as a file to download, in the formats the Download menu offers (pure). */

/** One deliverable in every form a download can take. */
export interface DeliverableParts {
  title: string;
  /** The agent's output as written. */
  markdown: string;
  /** The output rendered and sanitised. */
  html: string;
  /** The output as plain text, without Markdown markers. */
  text: string;
}

export type DownloadFormat = 'html' | 'txt' | 'md';

export interface DownloadFormatSpec {
  label: string;
  hint?: string;
  extension: string;
  mime: string;
  body: (parts: DeliverableParts) => string;
}

/** Characters a file system will not take in a name (Windows is the strictest). */
const FORBIDDEN = /[\\/:*?"<>|]/g;
const NAME_MAX_CHARS = 80;
const ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => ENTITIES[char]);
}

/** A whole HTML file around an already sanitised body, so Word or a browser opens it. */
export function htmlDocument(title: string, bodyHtml: string): string {
  return `<!doctype html><meta charset="utf-8"><title>${escapeHtml(title)}</title>${bodyHtml}`;
}

/** A title as a file name: no characters a file system refuses, at most 80, never empty. */
export function safeFileName(title: string): string {
  const name = title.replace(FORBIDDEN, '').trim().slice(0, NAME_MAX_CHARS).trim();
  return name || 'deliverable';
}

/** The Download menu's formats (Strategy + Registry, AGENTS.md §7): a new one is an entry. */
export const DOWNLOAD_FORMATS: Record<DownloadFormat, DownloadFormatSpec> = {
  html: {
    label: 'Formatted (.html)',
    hint: 'Opens in Word, Google Docs or a browser',
    extension: 'html',
    mime: 'text/html',
    body: (parts) => htmlDocument(parts.title, parts.html),
  },
  txt: {
    label: 'Plain text (.txt)',
    extension: 'txt',
    mime: 'text/plain',
    body: (parts) => parts.text,
  },
  md: {
    label: 'Markdown (.md)',
    extension: 'md',
    mime: 'text/markdown',
    body: (parts) => parts.markdown,
  },
};
