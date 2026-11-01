import DOMPurify from 'dompurify';
import { marked } from 'marked';

/**
 * Model output is untrusted text: a web page or a document the model read can steer
 * it. So the HTML that Markdown makes of it is sanitised, and narrowly. Beyond scripts,
 * nothing that could pass for the app's own screen survives: no form controls, no
 * `<style>`, no `style` or `class` attribute (the app's own Tailwind classes include
 * `fixed inset-0 z-50`), so a reply cannot draw a fake sign-in panel or lay an
 * invisible link over the page. Shared by chat and pipeline results (§3).
 */
const SANITIZE_CONFIG = {
  // HTML only: Markdown never makes SVG or MathML.
  USE_PROFILES: { html: true },
  FORBID_TAGS: [
    'form',
    'button',
    'textarea',
    'select',
    'option',
    'optgroup',
    'datalist',
    'fieldset',
    'legend',
    'label',
    'output',
    'dialog',
    'style',
  ],
  FORBID_ATTR: ['style', 'class'],
};

/**
 * Markdown makes one kind of input, a task-list box (`- [x] done`), drawn disabled.
 * Any input left in the HTML becomes exactly that, so nothing can be typed into one.
 */
function toTaskCheckbox(input: Element): void {
  const checked = input.hasAttribute('checked');
  for (const name of input.getAttributeNames()) input.removeAttribute(name);
  input.setAttribute('type', 'checkbox');
  input.setAttribute('disabled', '');
  if (checked) input.setAttribute('checked', '');
}

/** Where a picture the agents saved keeps its workspace path once its `src` is gone. */
export const WORKSPACE_PICTURE = 'data-workspace-path';

/** A relative address such as "images/hero.jpg": no scheme, not rooted at the site. */
const WORKSPACE_PATH = /^(?![a-z][\w+.-]*:)[^/]/i;

function decodedPath(src: string): string {
  try {
    return decodeURI(src);
  } catch {
    return src;
  }
}

/**
 * An agent shows a picture it saved by its workspace path. The browser would fetch
 * that from the page's own address, without the session header, and draw a broken
 * image; so the path moves to WORKSPACE_PICTURE for useWorkspacePictures to load.
 */
function toWorkspacePicture(image: Element): void {
  const src = image.getAttribute('src') ?? '';
  if (!WORKSPACE_PATH.test(src)) return;
  image.removeAttribute('src');
  image.setAttribute(WORKSPACE_PICTURE, decodedPath(src).replace(/^\.\//, ''));
}

/** What a kept element must look like once its attributes are sanitised (Strategy, by tag). */
const HARDEN_BY_TAG: Partial<Record<string, (element: Element) => void>> = {
  // A link opens in the same tab, as before (DOMPurify drops `target`), and never hands
  // the destination this window or the app's address.
  a: (link) => link.setAttribute('rel', 'noopener noreferrer'),
  img: toWorkspacePicture,
  input: toTaskCheckbox,
};

// A private instance: its hooks reach no other DOMPurify user, and since a module is
// evaluated once, they are added once.
const purifier = DOMPurify(window);
purifier.addHook('afterSanitizeAttributes', (element) => {
  HARDEN_BY_TAG[element.localName]?.(element);
});

export function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false });
  return purifier.sanitize(html, SANITIZE_CONFIG);
}

const HEADINGS = 'h1, h2, h3, h4, h5, h6';
/**
 * A cell holding one number, maybe signed, priced, a percentage or with a short unit:
 * "1,900", "-$4.60", "12 %", "3.9 s", "4.6 MB", "EUR 2.40".
 */
const NUMERIC_CELL = /^(?:[A-Z]{3}\s?)?[-+−]?[$€£¥]?\s?\d[\d\s.,]*(?:%|[A-Za-zµ]{1,3})?$/;

/**
 * Moves a text's own headings under the page's: its top heading becomes h{base} (`#`
 * usually, `##` in a text that starts there), the next level h{base + 1}, capped at h6, so
 * the outline skips no level. `data-level` keeps the size the writer meant.
 */
function nestHeadings(root: DocumentFragment, base: number): void {
  const headings = [...root.querySelectorAll(HEADINGS)];
  const top = Math.min(...headings.map((heading) => Number(heading.localName[1])));
  for (const heading of headings) {
    const level = Number(heading.localName[1]);
    const nested = document.createElement(`h${Math.min(6, base + level - top)}`);
    for (const { name, value } of heading.attributes) nested.setAttribute(name, value);
    nested.dataset.level = String(level);
    nested.append(...heading.childNodes);
    heading.replaceWith(nested);
  }
}

/** A box that scrolls sideways, reachable by keyboard and named for what it holds. */
function asScroller(box: HTMLElement, label: string): void {
  box.setAttribute('role', 'group');
  box.setAttribute('aria-label', label);
  box.tabIndex = 0;
}

/** A wide table scrolls sideways in its own focusable box instead of breaking words. */
function wrapTables(root: DocumentFragment): void {
  for (const table of root.querySelectorAll('table')) {
    const scroller = document.createElement('div');
    scroller.className = 'md-table-scroll';
    asScroller(scroller, 'Table');
    table.replaceWith(scroller);
    scroller.append(table);
  }
}

/** A code block scrolls sideways too (`pre` overflows), so it is focusable the same way. */
function focusableCode(root: DocumentFragment): void {
  for (const block of root.querySelectorAll('pre')) asScroller(block, 'Code');
}

function markNumbers(root: DocumentFragment): void {
  for (const cell of root.querySelectorAll('td')) {
    if (NUMERIC_CELL.test(cell.textContent?.trim() ?? '')) cell.dataset.num = '';
  }
}

/**
 * A model's Markdown as a reading document: sanitised like `renderMarkdown`, then its
 * headings nested from `headingBase`, its tables and code blocks scrollable by keyboard and its number cells
 * marked for right alignment. The marks are added to the sanitised DOM, never parsed
 * from text, and the model's own `data-*` attributes are dropped, so only this code
 * sets `data-level`, `data-num` or the scroller's class.
 */
export function renderDocument(text: string, headingBase: number): string {
  const html = marked.parse(text, { async: false });
  const root = purifier.sanitize(html, {
    ...SANITIZE_CONFIG,
    ALLOW_DATA_ATTR: false,
    RETURN_DOM_FRAGMENT: true,
  });
  nestHeadings(root, headingBase);
  wrapTables(root);
  focusableCode(root);
  markNumbers(root);
  const host = document.createElement('div');
  host.append(root);
  return host.innerHTML;
}
