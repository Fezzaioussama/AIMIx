import { describe, expect, it } from 'vitest';

import {
  DOWNLOAD_FORMATS,
  htmlDocument,
  safeFileName,
  type DeliverableParts,
} from './deliverableFiles';

const PARTS: DeliverableParts = {
  title: 'Blog post',
  markdown: '# Loop\n\n**Bold** words',
  html: '<h1>Loop</h1><p><strong>Bold</strong> words</p>',
  text: 'Loop\n\nBold words',
};

describe('safeFileName', () => {
  it('strips what a file system refuses, and trims', () => {
    expect(safeFileName('  Q3: plan / "draft" <v2>?*|\\  ')).toBe('Q3 plan  draft v2');
  });

  it('keeps at most 80 characters', () => {
    expect(safeFileName('a'.repeat(100))).toHaveLength(80);
    expect(safeFileName(`${'a'.repeat(79)} b`)).toBe('a'.repeat(79));
  });

  it('falls back to “deliverable”', () => {
    expect(safeFileName('')).toBe('deliverable');
    expect(safeFileName(' /:*? ')).toBe('deliverable');
  });
});

describe('htmlDocument', () => {
  it('is a whole HTML file with a charset and an escaped title', () => {
    expect(htmlDocument('<Title> & "more"', '<p>Hi</p>')).toBe(
      '<!doctype html><meta charset="utf-8"><title>&lt;Title&gt; &amp; &quot;more&quot;</title><p>Hi</p>',
    );
  });
});

describe('DOWNLOAD_FORMATS', () => {
  it('formatted: an HTML file of the rendered output, with a hint', () => {
    const format = DOWNLOAD_FORMATS.html;
    expect([format.label, format.hint, format.extension, format.mime]).toEqual([
      'Formatted (.html)',
      'Opens in Word, Google Docs or a browser',
      'html',
      'text/html',
    ]);
    expect(format.body(PARTS)).toBe(htmlDocument('Blog post', PARTS.html));
  });

  it('plain text: the text without Markdown', () => {
    const format = DOWNLOAD_FORMATS.txt;
    expect([format.label, format.hint, format.extension, format.mime]).toEqual([
      'Plain text (.txt)',
      undefined,
      'txt',
      'text/plain',
    ]);
    expect(format.body(PARTS)).toBe('Loop\n\nBold words');
  });

  it('Markdown: the output as the agent wrote it', () => {
    const format = DOWNLOAD_FORMATS.md;
    expect([format.label, format.extension, format.mime]).toEqual([
      'Markdown (.md)',
      'md',
      'text/markdown',
    ]);
    expect(format.body(PARTS)).toBe(PARTS.markdown);
  });
});
