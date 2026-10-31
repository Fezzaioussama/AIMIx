import {
  File as FileIcon,
  FileCode,
  FileImage,
  FileJson,
  FileSpreadsheet,
  FileText,
  type LucideIcon,
} from 'lucide-react';

import type { FileListing, WorkspaceFile } from '../../core/api/types';

/** An icon per file type (the extension without its dot); anything else is a plain file. */
const ICONS: Record<string, LucideIcon> = {
  pdf: FileText,
  docx: FileText,
  txt: FileText,
  md: FileText,
  csv: FileSpreadsheet,
  json: FileJson,
  yaml: FileJson,
  yml: FileJson,
  html: FileCode,
  jpg: FileImage,
  jpeg: FileImage,
  png: FileImage,
  webp: FileImage,
};

/** The types a browser shows as a picture: what generate_image saves (JPEG), and more. */
const PICTURE_TYPES = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif']);

/** How the upload hint names each type, for people rather than for file systems, in
 *  the order it lists them: the most common first. */
const TYPE_NAMES: Record<string, string> = {
  '.pdf': 'PDF',
  '.docx': 'Word',
  '.txt': 'text',
  '.md': 'Markdown',
  '.csv': 'CSV',
  '.json': 'JSON',
  '.yaml': 'YAML',
  '.yml': 'YAML',
  '.html': 'HTML',
};

export function fileIcon(type: string): LucideIcon {
  return ICONS[type] ?? FileIcon;
}

export function isPicture(type: string): boolean {
  return PICTURE_TYPES.has(type);
}

/** The last part of a path: "reports/q3.pdf" → "q3.pdf". */
export function fileName(path: string): string {
  return path.slice(path.lastIndexOf('/') + 1);
}

/** The folders before the name, or '' for a file at the top. */
export function folderOf(path: string): string {
  return path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
}

/** Decimal units, as the server states its limits: "340 KB", "1.5 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} ${bytes === 1 ? 'byte' : 'bytes'}`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1000;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value >= 10 ? Math.round(value) : Number(value.toFixed(1))} ${units[unit]}`;
}

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

export function formatDate(iso: string): string {
  return DATE_FORMAT.format(new Date(iso));
}

/** "PDF, Word, text and CSV": the accepted types in plain words, without repeats. */
export function describeTypes(extensions: string[]): string {
  const known = Object.keys(TYPE_NAMES).filter((ext) => extensions.includes(ext));
  const others = extensions.filter((ext) => !(ext in TYPE_NAMES));
  const names = [
    ...new Set([
      ...known.map((ext) => TYPE_NAMES[ext]),
      ...others.map((ext) => ext.replace('.', '').toUpperCase()),
    ]),
  ];
  if (names.length < 2) return names.join('');
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/** The listing with `file` added at the top, replacing one of the same path. */
export function withFile(listing: FileListing, file: WorkspaceFile): FileListing {
  return withFiles(listing, [file, ...listing.files.filter((entry) => entry.path !== file.path)]);
}

export function withoutFile(listing: FileListing, path: string): FileListing {
  return withFiles(
    listing,
    listing.files.filter((entry) => entry.path !== path),
  );
}

/** What the storage limit counts is the sum of the sizes, as on the server. */
function withFiles(listing: FileListing, files: WorkspaceFile[]): FileListing {
  return { ...listing, files, used_bytes: files.reduce((total, file) => total + file.size, 0) };
}
