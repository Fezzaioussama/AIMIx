import { describe, expect, it } from 'vitest';

import { renderMarkdown } from './renderMarkdown';

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
