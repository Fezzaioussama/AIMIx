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

/** What a kept element must look like once its attributes are sanitised (Strategy, by tag). */
const HARDEN_BY_TAG: Partial<Record<string, (element: Element) => void>> = {
  // A link opens in the same tab, as before (DOMPurify drops `target`), and never hands
  // the destination this window or the app's address.
  a: (link) => link.setAttribute('rel', 'noopener noreferrer'),
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
