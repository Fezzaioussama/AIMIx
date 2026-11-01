/**
 * Web links in what people type: finding them and naming them briefly. Agents cannot open
 * a link on their own, so a page is read into the text first (`importDocumentFromUrl`).
 */

/** Characters a link's label keeps: enough for a host and the end of its path. */
const LABEL_CHARS = 48;
const LINK = /https?:\/\/[^\s<>"'`]+/gi;
/** Punctuation that ends a sentence rather than a link: "see https://example.com/a." */
const TRAILING = /[.,;:!?'"]+$/;
const OPENERS: Record<string, string> = { ')': '(', ']': '[' };

/** `text` as an http(s) address, or null when it is not one. */
function parsed(text: string): URL | null {
  try {
    const url = new URL(text);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url : null;
  } catch {
    return null;
  }
}

function occurrences(text: string, char: string): number {
  return text.split(char).length - 1;
}

/** A link found in text, without what follows it, keeping a closing bracket it opened. */
function trimmed(link: string): string {
  const cut = link.replace(TRAILING, '');
  const last = cut.at(-1) ?? '';
  const opener = Object.hasOwn(OPENERS, last) ? OPENERS[last] : null;
  if (opener === null || occurrences(cut, last) <= occurrences(cut, opener)) return cut;
  return trimmed(cut.slice(0, -1));
}

export function isWebAddress(text: string): boolean {
  return parsed(text) !== null;
}

/** The http(s) links in a text, in order. */
export function linksIn(text: string): string[] {
  return [...text.matchAll(LINK)].map((match) => trimmed(match[0])).filter(isWebAddress);
}

/** The link a field holds when it holds nothing else, as typed; else null. */
export function bareLink(value: string): string | null {
  const text = value.trim();
  return /\s/.test(text) || !isWebAddress(text) ? null : text;
}

/** A typed address as one the server can open (https:// added when left out), or null. */
export function toWebAddress(typed: string): string | null {
  const text = typed.trim();
  if (!text || /\s/.test(text)) return null;
  return parsed(/^[a-z][a-z\d+.-]*:/i.test(text) ? text : `https://${text}`)?.href ?? null;
}

/** Whether two links lead to the same address, however each was written. */
export function sameAddress(first: string, second: string): boolean {
  const a = parsed(first);
  return a !== null && a.href === parsed(second)?.href;
}

function decoded(text: string): string {
  try {
    return decodeURI(text);
  } catch {
    return text;
  }
}

/** `text` cut to `max` characters in the middle, so both ends stay readable. */
function shortened(text: string, max: number): string {
  if (text.length <= max) return text;
  const head = Math.ceil((max - 1) / 2);
  return `${text.slice(0, head)}…${text.slice(text.length - (max - 1 - head))}`;
}

function hostOf(url: URL): string {
  return url.hostname.replace(/^www\./, '');
}

/** The site a link is on, as people say it: "example.com". */
export function linkHost(address: string): string {
  const url = parsed(address);
  return url === null ? address : hostOf(url);
}

/** A link as people read it: host and path, without "https://" or "www.", shortened. */
export function linkLabel(address: string): string {
  const url = parsed(address);
  if (url === null) return address;
  const path = url.pathname === '/' ? '' : decoded(url.pathname);
  return shortened(`${hostOf(url)}${path}`, LABEL_CHARS);
}

/** A document's name as shown: a file by its own name, a page by its link's label. */
export function sourceLabel(name: string): string {
  return isWebAddress(name) ? linkLabel(name) : name;
}
