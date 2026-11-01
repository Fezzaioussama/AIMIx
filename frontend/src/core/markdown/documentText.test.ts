import { afterEach, describe, expect, it } from 'vitest';

import { countWords, plainTextOf } from './documentText';
import { renderDocument, renderMarkdown } from './renderMarkdown';

const plain = (markdown: string) => plainTextOf(renderMarkdown(markdown));

describe('plainTextOf', () => {
  it('separates headings and paragraphs with a blank line', () => {
    expect(plain('# Title\n\nText')).toBe('Title\n\nText');
  });

  it('reads a soft line break as a space and a hard one as a new line', () => {
    expect(plain('one\ntwo  \nthree')).toBe('one two\nthree');
  });

  it('writes bullets and numbers, nested items indented two spaces', () => {
    expect(plain('- one\n  - inner\n- two\n\n3. third\n4. fourth')).toBe(
      '• one\n  • inner\n• two\n\n3. third\n4. fourth',
    );
  });

  it('keeps whether a task is done', () => {
    expect(plain('- [x] done\n- [ ] todo')).toBe('• ☑ done\n• ☐ todo');
  });

  it('separates table cells with tabs and rows with new lines', () => {
    expect(plain('| City | Price |\n|--|--:|\n| Paris | 1,900 |\n| Lyon | 950 |')).toBe(
      'City\tPrice\nParis\t1,900\nLyon\t950',
    );
  });

  it('reads a table the same inside its scroller', () => {
    const html = renderDocument('# Costs\n\n| City | Price |\n|--|--|\n| Paris | 1,900 |', 3);

    expect(plainTextOf(html)).toBe('Costs\n\nCity\tPrice\nParis\t1,900');
  });

  it('names a link’s address once, and not at all twice', () => {
    expect(plain('See [Loop](https://loop.example/a) or https://loop.example/b.')).toBe(
      'See Loop (https://loop.example/a) or https://loop.example/b.',
    );
  });

  it('keeps code blocks as written', () => {
    expect(plain('```\nif (a) {\n  b();\n}\n```')).toBe('if (a) {\n  b();\n}');
  });

  it('leaves no Markdown marker behind', () => {
    const text = plain('# Plan\n\n**Bold** and _soft_ and `code`.\n\n> Quoted\n\n---\n\n## Next');

    expect(text).toBe('Plan\n\nBold and soft and code.\n\nQuoted\n\nNext');
    expect(text).not.toMatch(/\*\*|#|`|>/);
  });

  it('keeps a picture’s alt text', () => {
    expect(plain('Look: ![A loyalty card](card.png)')).toBe('Look: A loyalty card');
  });

  it('reads spaces that meet across tags as one', () => {
    expect(plainTextOf('<p>Loop <em> rewards</em>  <strong>you</strong></p>')).toBe(
      'Loop rewards you',
    );
  });

  it('never leaves more than one blank line', () => {
    expect(plainTextOf('<p>a</p><hr><hr><p>b</p><div></div><p>c</p>')).toBe('a\n\nb\n\nc');
  });
});

describe('countWords', () => {
  const segmenter = Intl.Segmenter;
  afterEach(() => {
    Object.defineProperty(Intl, 'Segmenter', {
      value: segmenter,
      configurable: true,
      writable: true,
    });
  });

  it('counts the words of an English paragraph', () => {
    expect(countWords('Loop turns every coffee into a reward. Don’t miss it!')).toBe(10);
  });

  it('counts a number as a word', () => {
    expect(countWords('We served 1,900 people in 2024')).toBe(6);
  });

  it('counts nothing in an empty text', () => {
    expect(countWords('  ')).toBe(0);
  });

  it('still counts without Intl.Segmenter', () => {
    Reflect.deleteProperty(Intl, 'Segmenter');
    expect('Segmenter' in Intl).toBe(false);

    expect(countWords('Loop turns every coffee into a reward')).toBe(7);
    expect(countWords('Café crème, 3 times')).toBe(4);
  });
});
