import type {
  Integration,
  IntegrationHeader,
  IntegrationHeaderInput,
  IntegrationInput,
  IntegrationPatch,
} from '../../core/api/types';

/** Mirrors INTEGRATION_NAME_PATTERN in backend/api/models.py. */
const NAME_PATTERN = /^[a-z][a-z0-9_]{1,30}$/;
const NAME_MAX_LENGTH = 31;
const URL_PATTERN = /^https?:\/\/\S+$/i;

export interface HeaderDraft {
  name: string;
  /** A newly typed value. Empty keeps the saved value of a row that has one. */
  value: string;
  /** The saved header this row was loaded from; null for a new row. */
  saved: IntegrationHeader | null;
}

/** The add/edit form of one integration. */
export interface IntegrationDraft {
  name: string;
  url: string;
  headers: HeaderDraft[];
}

export function emptyHeader(): HeaderDraft {
  return { name: '', value: '', saved: null };
}

export function emptyDraft(): IntegrationDraft {
  return { name: '', url: '', headers: [] };
}

export function draftFrom(integration: Integration): IntegrationDraft {
  return {
    name: integration.name,
    url: integration.url,
    headers: integration.headers.map((saved) => ({ name: saved.name, value: '', saved })),
  };
}

/** Names prefix tool names, so they are typed as snake_case. */
export function toIntegrationName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .slice(0, NAME_MAX_LENGTH);
}

/** The server's host, e.g. "mcp.example.com", for the list. */
export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function originOf(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/** Saved header values only go to the server they were entered for. */
export function addressChanged(draft: IntegrationDraft, saved: Integration | null): boolean {
  if (!saved || saved.headers.length === 0) return false;
  return originOf(draft.url.trim()) !== originOf(saved.url);
}

/** A saved row left blank, and not renamed, keeps its saved value. */
export function keepsSavedValue(row: HeaderDraft): boolean {
  return (
    row.saved !== null &&
    !row.value.trim() &&
    row.name.trim().toLowerCase() === row.saved.name.toLowerCase()
  );
}

function isBlank(row: HeaderDraft): boolean {
  return !row.name.trim() && !row.value.trim();
}

function filled(rows: HeaderDraft[]): HeaderDraft[] {
  return rows.filter((row) => !isBlank(row));
}

function headersProblem(rows: HeaderDraft[], moved: boolean): string | null {
  if (rows.some((row) => !row.name.trim())) return 'Give every header a name.';
  const names = rows.map((row) => row.name.trim().toLowerCase());
  if (new Set(names).size !== names.length) return 'Each header may appear only once.';
  const missing = rows.some((row) => !row.value.trim() && (moved || !keepsSavedValue(row)));
  if (!missing) return null;
  return moved
    ? 'You changed the server address: enter every header value again.'
    : 'Give every new header a value.';
}

/** Why the form cannot be saved yet, in plain words, or null when it can. */
export function draftProblem(draft: IntegrationDraft, saved: Integration | null): string | null {
  if (!NAME_PATTERN.test(draft.name)) {
    return 'The name needs 2 to 31 characters: lowercase letters, numbers or _, starting with a letter.';
  }
  if (!URL_PATTERN.test(draft.url.trim())) {
    return 'Paste the full server URL, starting with https://.';
  }
  return headersProblem(filled(draft.headers), addressChanged(draft, saved));
}

function headerInputs(rows: HeaderDraft[]): IntegrationHeaderInput[] {
  return filled(rows).map((row) => {
    const name = row.name.trim();
    return keepsSavedValue(row) ? { name } : { name, value: row.value.trim() };
  });
}

function headersChanged(rows: HeaderDraft[], saved: IntegrationHeader[]): boolean {
  const kept = filled(rows);
  return (
    kept.length !== saved.length ||
    kept.some((row, index) => !keepsSavedValue(row) || row.name.trim() !== saved[index].name)
  );
}

export function toCreate(draft: IntegrationDraft): IntegrationInput {
  return { name: draft.name, url: draft.url.trim(), headers: headerInputs(draft.headers) };
}

/** The PATCH body: only what changed, and the whole header list when any header did. */
export function toPatch(draft: IntegrationDraft, saved: Integration): IntegrationPatch {
  const url = draft.url.trim();
  return {
    ...(draft.name !== saved.name ? { name: draft.name } : {}),
    ...(url !== saved.url ? { url } : {}),
    ...(headersChanged(draft.headers, saved.headers)
      ? { headers: headerInputs(draft.headers) }
      : {}),
  };
}
