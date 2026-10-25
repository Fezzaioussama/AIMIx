/** A request to approve a tool call, in plain words (the card's pure helpers). */

/** A value longer than this, or with more lines, is folded behind "Show all". */
export const FOLD_AFTER_CHARS = 160;
const FOLD_AFTER_LINES = 4;
/** How much of a folded value stays visible. */
const PREVIEW_CHARS = 100;

/**
 * "Send email" from `crm_send_email` of `crm`: the integration's prefix and the
 * underscores go, so the tool reads as what it does.
 */
export function toolLabel(name: string, source: string): string {
  const bare = name.startsWith(`${source}_`) ? name.slice(source.length + 1) : name;
  const words = bare.replace(/[_-]+/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : name;
}

/** One argument as people read it. */
export interface ArgumentRow {
  key: string;
  text: string;
  /** Too long to show in full at first. */
  folded: boolean;
  /** The start of a folded value, on one line. */
  preview: string;
}

function isPlain(value: unknown): value is string | number | boolean | null {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value);
}

/** Text as written, numbers and flags as words, lists of plain values on one line. */
function valueText(value: unknown): string {
  if (value === null) return '(empty)';
  if (typeof value === 'string') return value;
  if (isPlain(value)) return String(value);
  if (Array.isArray(value) && value.length > 0 && value.every(isPlain)) {
    return value.map(valueText).join(', ');
  }
  return JSON.stringify(value, null, 2);
}

function toRow(key: string, value: unknown): ArgumentRow {
  const text = valueText(value);
  const folded = text.length > FOLD_AFTER_CHARS || text.split('\n').length > FOLD_AFTER_LINES;
  const preview = `${text.slice(0, PREVIEW_CHARS).replace(/\s+/g, ' ').trim()}…`;
  return { key, text, folded, preview };
}

/** The call's arguments as rows, in the order the model gave them. */
export function argumentRows(args: Record<string, unknown>): ArgumentRow[] {
  return Object.entries(args).map(([key, value]) => toRow(key, value));
}

/** What is left of a request's time: "45 s left", "9 min 05 s left", "28 min left". */
export function formatTimeLeft(ms: number): string {
  if (ms <= 0) return 'Time is up';
  const seconds = Math.ceil(ms / 1000);
  if (seconds < 60) return `${seconds} s left`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 10) return `${minutes} min ${String(seconds % 60).padStart(2, '0')} s left`;
  return `${Math.ceil(seconds / 60)} min left`;
}
