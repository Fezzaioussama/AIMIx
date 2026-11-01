/**
 * Plain text and word counts for rendered Markdown: what a "Copy" pastes into a
 * plain-text field and what a byline counts. It reads the HTML the renderer made,
 * so no Markdown marker (`**`, `#`, `|`) survives.
 */

type BlockText = (element: Element, depth: number) => string;

const INDENT = '  ';
// HTML's own whitespace; `\s` would also swallow a no-break space the writer meant.
const HTML_SPACE = /[ \t\n\r\f]+/g;

/** Inline elements that read as something other than their text (Strategy, by tag). */
const INLINE: Partial<Record<string, (element: Element) => string>> = {
  a: linkText,
  img: (image) => image.getAttribute('alt') ?? '',
  br: () => '\n',
  input: (box) => (box.hasAttribute('checked') ? '☑ ' : '☐ '),
};

function inlineText(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return (node.textContent ?? '').replace(HTML_SPACE, ' ');
  if (!(node instanceof Element)) return '';
  const read = INLINE[node.localName];
  return read ? read(node) : childrenText(node);
}

function childrenText(element: Element): string {
  return [...element.childNodes].map(inlineText).join('');
}

/** "Loop (https://…)", or the address alone when it is its own text. */
function linkText(link: Element): string {
  const text = tidy(childrenText(link));
  const href = link.getAttribute('href') ?? '';
  if (!href || text === href) return text;
  return text ? `${text} (${href})` : href;
}

/** Trims every line of a run of inline text, and spaces that meet across tags to one. */
function tidy(text: string): string {
  return text
    .split('\n')
    .map((line) => line.replace(/ {2,}/g, ' ').trim())
    .join('\n')
    .trim();
}

function listText(list: Element, depth: number, marker: (index: number) => string): string {
  const indent = INDENT.repeat(depth);
  return [...list.children]
    .map((item, index) => `${indent}${marker(index)}${sectionText(item, depth + 1, '\n')}`)
    .join('\n');
}

function orderedText(list: Element, depth: number): string {
  const start = Number(list.getAttribute('start') ?? 1);
  const first = Number.isFinite(start) ? start : 1;
  return listText(list, depth, (index) => `${first + index}. `);
}

function tableText(table: Element): string {
  return [...table.querySelectorAll('tr')]
    .map((row) => [...row.children].map((cell) => tidy(childrenText(cell))).join('\t'))
    .join('\n');
}

const asText: BlockText = (element) => tidy(childrenText(element));
const asSection: BlockText = (element, depth) => sectionText(element, depth);

/** How each block element reads as plain text (Strategy, by tag). */
const BLOCKS: Partial<Record<string, BlockText>> = {
  h1: asText,
  h2: asText,
  h3: asText,
  h4: asText,
  h5: asText,
  h6: asText,
  p: asText,
  blockquote: asSection,
  div: asSection,
  ul: (list, depth) => listText(list, depth, () => '• '),
  ol: orderedText,
  table: tableText,
  pre: (block) => (block.textContent ?? '').replace(/\n$/, ''),
  hr: () => '',
};

/** A block element's text, or null for inline content. */
function blockText(node: Node, depth: number): string | null {
  if (!(node instanceof Element)) return null;
  const read = BLOCKS[node.localName];
  return read ? read(node, depth) : null;
}

/** A container's blocks, each separated by `separator`; loose inline text is one block. */
function sectionText(parent: ParentNode, depth: number, separator = '\n\n'): string {
  const parts: string[] = [];
  let run = '';
  for (const node of parent.childNodes) {
    const block = blockText(node, depth);
    if (block === null) {
      run += inlineText(node);
      continue;
    }
    parts.push(tidy(run), block);
    run = '';
  }
  parts.push(tidy(run));
  return parts.filter(Boolean).join(separator);
}

/** The plain text of rendered HTML: blank lines between blocks, "• " and "1. " for lists. */
export function plainTextOf(html: string): string {
  const template = document.createElement('template');
  template.innerHTML = html;
  return sectionText(template.content, 0).replace(/\n{3,}/g, '\n\n');
}

/** Words in a text, as a reader would count them ("1,900" is one). */
export function countWords(text: string): number {
  if (typeof Intl.Segmenter !== 'function') return text.match(/[\p{L}\p{N}]+/gu)?.length ?? 0;
  let words = 0;
  for (const part of new Intl.Segmenter(undefined, { granularity: 'word' }).segment(text)) {
    if (part.isWordLike) words += 1;
  }
  return words;
}
